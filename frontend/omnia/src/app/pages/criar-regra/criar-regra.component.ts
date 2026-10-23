import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { TagComponent } from '../../components/tag/tag.component';
import { ProcessosApiService } from '../../services/processos-api.service';

export interface Msg {
  autor: 'user' | 'ia';
  texto: string;
}

@Component({
  selector: 'app-criar-regra',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    FormsModule,
    AppShellComponent,
    PanelComponent,
    TagComponent,
  ],
  templateUrl: './criar-regra.component.html',
  styleUrl: './criar-regra.component.scss',
})
export class CriarRegraComponent {
  private readonly api = inject(ProcessosApiService);
  // Estados reativos (Signals)
  instrucao = signal<string>(
    'Verifique se existem processos arquivados definitivamente nos quais tenha sido determinada a expedição de ofício, mas não exista registro posterior de expedição ou cumprimento.'
  );
  atende = signal<string>('Há certidão ou documento comprovando a expedição do ofício.');
  naoAtende = signal<string>('Arquivamento definitivo sem qualquer registro posterior de cumprimento.');
  naoEncaixa = signal<string>('Processos sem determinação de expedição de ofício.');
  ajustes = signal<string>('');

  mensagens = signal<Msg[]>([
    {
      autor: 'ia',
      texto:
        'Descreva a verificação desejada e informe os cenários de atendimento, de não atendimento e de não enquadramento. Vou transformar tudo em uma sequência de passos auditáveis.',
    },
  ]);

  passos = signal<string[] | null>(null);
  aprovado = signal<boolean>(false);
  nome = signal<string>('Arquivamento com possível pendência');
  descricao = signal<string>(
    'Sinaliza arquivamentos definitivos sem registro posterior de cumprimento de determinação judicial.'
  );
  salva = signal<boolean>(false);
  gerando = signal<boolean>(false);
  salvando = signal<boolean>(false);
  erro = signal<string | null>(null);
  regraId = signal<string | null>(null);

  enviar(): void {
    if (this.gerando()) return;
    this.erro.set(null);
    this.aprovado.set(false);
    this.salva.set(false);
    this.regraId.set(null);
    this.passos.set(null);
    const textoUsuario = `${this.instrucao()}\n\nAtende: ${this.atende()}\nNão atende: ${this.naoAtende()}\nNão se encaixa: ${this.naoEncaixa()}${this.ajustes().trim() ? `\nAjustes solicitados: ${this.ajustes().trim()}` : ''}`;
    this.mensagens.update((m) => [
      ...m,
      { autor: 'user', texto: textoUsuario },
    ]);
    this.gerando.set(true);
    this.api.gerarPassosRegra({
      instrucao: this.instrucao(),
      atende: this.atende(),
      nao_atende: this.naoAtende(),
      nao_se_encaixa: this.naoEncaixa(),
      ajustes: this.ajustes().trim() || null,
    }).subscribe({
      next: ({ passos }) => {
        this.passos.set(passos);
        this.mensagens.update((m) => [...m, {
          autor: 'ia',
          texto: 'A IA estruturou os passos abaixo com base na instrução e nos cenários informados. Revise antes de aprovar.',
        }]);
        this.gerando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        const detalhe = error.error?.detail;
        this.erro.set(typeof detalhe === 'string' ? detalhe : 'Não foi possível gerar os passos. Verifique a conexão com o backend e tente novamente.');
        this.mensagens.update((m) => [...m, { autor: 'ia', texto: 'Não consegui gerar os passos agora. Corrija o problema indicado e tente novamente.' }]);
        this.gerando.set(false);
      },
    });
  }

  aprovarPassos(): void {
    this.aprovado.set(true);
  }

  salvarRegra(): void {
    if (this.salvando() || !this.passos()) return;
    this.erro.set(null);
    this.salvando.set(true);
    this.api.salvarRegra({
      instrucao: this.instrucao(),
      atende: this.atende(),
      nao_atende: this.naoAtende(),
      nao_se_encaixa: this.naoEncaixa(),
      ajustes: this.ajustes().trim() || null,
      nome: this.nome(),
      descricao: this.descricao(),
      passos: this.passos()!,
    }).subscribe({
      next: (regra) => {
        this.regraId.set(regra.id);
        this.salva.set(true);
        this.salvando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        const detalhe = error.error?.detail;
        this.erro.set(typeof detalhe === 'string' ? detalhe : 'Não foi possível salvar a regra. Verifique a conexão com o backend e tente novamente.');
        this.salvando.set(false);
      },
    });
  }
}

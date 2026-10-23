import { Component, signal, computed, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { TagComponent } from '../../components/tag/tag.component';  

import {
  biblioteca,
  detalhesRegra,
  RegraBiblioteca,
  DetalheRegraInfo,
} from '../../mock-data/prototype-data';
import { ProcessosApiService } from '../../services/processos-api.service';

@Component({
  selector: 'app-checklist',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    AppShellComponent,
    PanelComponent,
    TagComponent,
  ],
  templateUrl: './checklist.component.html',
  styleUrl: './checklist.component.scss',
})
export class ChecklistComponent implements OnInit {
  private readonly api = inject(ProcessosApiService);
  private readonly bibliotecaLista = signal<RegraBiblioteca[]>(biblioteca);
  get biblioteca(): RegraBiblioteca[] {
    return this.bibliotecaLista();
  }

  ngOnInit(): void {
    this.api.listarRegras().subscribe({
      next: (regras) => this.bibliotecaLista.set(regras),
      error: () => this.bibliotecaLista.set(biblioteca),
    });
  }

  regrasPendentes = signal([
    { 
      id: 'PEND-01', 
      nome: 'Verificação de prescrição intercorrente', 
      autor: 'João Silva', 
      dataEnvio: '15/08/2026',
      descricao: 'Regra destinada a analisar se o processo físico ou eletrônico encontra-se paralisado por tempo superior ao prazo prescricional da pretensão executória.',
      passos: ['Verificar data do último andamento processual', 'Identificar se há suspensão ativa', 'Calcular prazo decorrido']
    },
    { 
      id: 'PEND-02', 
      nome: 'Controle de prazos excedidos', 
      autor: 'Maria Souza', 
      dataEnvio: '16/08/2026',
      descricao: 'Identifica processos conclusos ao magistrado ou na secretaria com prazos legais ou judiciais extrapolados.',
      passos: ['Filtrar processos por localizador', 'Comparar data limite com a data atual', 'Sinalizar processos em atraso']
    },
    { 
      id: 'PEND-03', 
      nome: 'Análise de custas pendentes', 
      autor: 'Carlos Santos', 
      dataEnvio: '17/08/2026',
      descricao: 'Regra que verifica se houve o recolhimento das custas processuais ao final do processo antes do arquivamento.',
      passos: ['Consultar trânsito em julgado', 'Verificar guias de custas vinculadas', 'Confirmar status de pagamento no sistema']
    }
  ]);

  gruposDeRegras = signal([
    { 
      id: 'GR-01', 
      nome: 'Pacote Execução Fiscal', 
      descricao: 'Conjunto padrão de verificações recomendadas para varas de execução fiscal.',
      regras: [this.biblioteca[0], this.biblioteca[1]].filter(Boolean)
    },
    { 
      id: 'GR-02', 
      nome: 'Pacote Família e Sucessões', 
      descricao: 'Regras essenciais para auditoria em processos de família.',
      regras: [this.biblioteca[2]].filter(Boolean)
    },
    { 
      id: 'GR-03', 
      nome: 'Gabinete Criminal', 
      descricao: 'Verificações de prazos e prescrições criminais.',
      regras: [this.biblioteca[3]].filter(Boolean)
    }
  ]);
  
  // Estado do modal de detalhes (Signal)
  detalheId = signal<string | null>(null);

  grupoExpandidoId = signal<string | null>(null);

  // Controle do drop-down de pendências
  pendenciasAberto = signal(false);

  // Paginação - Controle de páginas
  paginaBiblioteca = signal(1);
  itensPorPaginaBiblioteca = 10;

  paginaPendentes = signal(1);
  itensPorPaginaPendentes = 5;

  // Paginação - Listas Computadas (Cortam as listas originais)
  bibliotecaPaginada = computed(() => {
    const inicio = (this.paginaBiblioteca() - 1) * this.itensPorPaginaBiblioteca;
    return this.biblioteca.slice(inicio, inicio + this.itensPorPaginaBiblioteca);
  });

  totalPaginasBiblioteca = computed(() => 
    Math.ceil(this.biblioteca.length / this.itensPorPaginaBiblioteca) || 1
  );

  regrasPendentesPaginadas = computed(() => {
    const inicio = (this.paginaPendentes() - 1) * this.itensPorPaginaPendentes;
    return this.regrasPendentes().slice(inicio, inicio + this.itensPorPaginaPendentes);
  });

  totalPaginasPendentes = computed(() => 
    Math.ceil(this.regrasPendentes().length / this.itensPorPaginaPendentes) || 1
  );

  toggleGrupo(id: string): void {
    // Se clicar no que já está aberto, ele fecha. Se não, ele abre o novo.
    this.grupoExpandidoId.update(atual => atual === id ? null : id);
  }

  // Novo sinal para controlar qual grupo está aberto no modal de edição
  grupoEmEdicao = signal<any | null>(null);

  // Substitua a sua função editarGrupo atual por esta:
  editarGrupo(id: string, event: Event): void {
    event.stopPropagation();
    const grupo = this.gruposDeRegras().find(g => g.id === id);
    if (grupo) {
      this.grupoEmEdicao.set(grupo);
    }
  }

  // Novo sinal para controlar se a área de adição está visível
  adicionandoRegra = signal(false);

  // Lista calculada: mostra apenas as regras da biblioteca que NÃO estão no grupo atual
  regrasDisponiveisParaGrupo = computed(() => {
    const grupo = this.grupoEmEdicao();
    if (!grupo) return [];
    
    return this.biblioteca.filter(
      (regraBib) => !grupo.regras.some((regraGrupo: any) => regraGrupo.id === regraBib.id)
    );
  });

  // Funções de controle da adição
  iniciarAdicaoRegra(): void {
    this.adicionandoRegra.set(true);
  }

  cancelarAdicaoRegra(): void {
    this.adicionandoRegra.set(false);
  }

  confirmarAdicaoRegra(novaRegra: any): void {
    const grupoAtual = this.grupoEmEdicao();
    if (grupoAtual) {
      // 1. Atualiza a lista geral de grupos
      this.gruposDeRegras.update(grupos =>
        grupos.map(g => {
          if (g.id === grupoAtual.id) {
            return { ...g, regras: [...g.regras, novaRegra] };
          }
          return g;
        })
      );
      
      // 2. Atualiza o modal na mesma hora
      this.grupoEmEdicao.set({
        ...grupoAtual,
        regras: [...grupoAtual.regras, novaRegra]
      });
      
      this.adicionandoRegra.set(false);
    }
  }

  // ATUALIZAÇÃO: Garante que o painel feche ao sair do modal
  fecharEdicaoGrupo(): void {
    this.grupoEmEdicao.set(null);
    this.adicionandoRegra.set(false);
  }

  removerRegraDoGrupo(grupoId: string, regraId: string): void {
    this.gruposDeRegras.update(grupos =>
      grupos.map(g => {
        if (g.id === grupoId) {
          return { ...g, regras: g.regras.filter((r: any) => r.id !== regraId) };
        }
        return g;
      })
    );
  }

  salvarEdicaoGrupo(): void {
    this.fecharEdicaoGrupo();
    // Em um sistema real, aqui você enviaria os dados para a API
  }

  // Regra selecionada computada
  regra = computed<RegraBiblioteca | undefined>(() =>
    this.biblioteca.find((r) => r.id === this.detalheId())
  );

  // Detalhes da regra computados
  detalhesInfo = computed<DetalheRegraInfo | undefined>(() => {
    const id = this.detalheId();
    return id ? detalhesRegra[id] : undefined;
  });

  abrirDetalhes(id: string): void {
    this.detalheId.set(id);
  }

  fecharDetalhes(): void {
    this.detalheId.set(null);
  }

  pendenteId = signal<string | null>(null);

  modoRevisao = signal(false);
  textoObservacao = signal('');

  
  regraPendenteSelecionada = computed(() => 
    this.regrasPendentes().find(r => r.id === this.pendenteId())
  );

  abrirDetalhesPendente(id: string): void {
    this.pendenteId.set(id);
  }

  fecharDetalhesPendente(): void {
    this.pendenteId.set(null);
    this.modoRevisao.set(false);
    this.textoObservacao.set('');
  }

  autorizarRegra(id: string): void {
    // Remove a regra da lista para simular a autorização
    this.regrasPendentes.update(regras => regras.filter(r => r.id !== id));
    this.fecharDetalhesPendente();
    alert('Regra autorizada com sucesso e adicionada à biblioteca!');
  }

  removerRegra(id: string): void {
    // Remove a regra da lista para simular a rejeição/remoção
    this.regrasPendentes.update(regras => regras.filter(r => r.id !== id));
    this.fecharDetalhesPendente();
  }

  iniciarRevisao(): void {
    this.modoRevisao.set(true);
  }

  cancelarRevisao(): void {
    this.modoRevisao.set(false);
    this.textoObservacao.set('');
  }

  atualizarObservacao(event: Event): void {
    const input = event.target as HTMLTextAreaElement;
    this.textoObservacao.set(input.value);
  }

  enviarParaRevisao(id: string): void {
    if (!this.textoObservacao().trim()) {
      alert('Por favor, insira uma observação para orientar o autor.');
      return;
    }
    
    // Remove da lista para simular o reenvio ao autor
    this.regrasPendentes.update(regras => regras.filter(r => r.id !== id));
    this.fecharDetalhesPendente();
    alert('Regra devolvida ao autor com as suas observações!');
  }

  togglePendencias(): void {
    this.pendenciasAberto.update(val => !val);
  }

  mudarPaginaBiblioteca(pagina: number): void {
    if (pagina >= 1 && pagina <= this.totalPaginasBiblioteca()) {
      this.paginaBiblioteca.set(pagina);
    }
  }

  mudarPaginaPendentes(pagina: number): void {
    if (pagina >= 1 && pagina <= this.totalPaginasPendentes()) {
      this.paginaPendentes.set(pagina);
    }
  }
}

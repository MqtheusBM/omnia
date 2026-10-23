import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { CorreicaoStatus, JobStatus, ProcessosApiService } from '../../services/processos-api.service';

import {
  correicaoPorProcesso,
  processos,
  Processo,
  ItemVeredito,
  Veredito,
} from '../../mock-data/prototype-data';

@Component({
  selector: 'app-aprovacao',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    AppShellComponent,
    PanelComponent,
  ],
  templateUrl: './aprovacao.component.html',
  styleUrl: './aprovacao.component.scss',
})
export class AprovacaoComponent implements OnInit {
  private readonly processosApi = inject(ProcessosApiService);
  private readonly route = inject(ActivatedRoute);
  processos: Processo[] = processos;
  linhasPadrao: ItemVeredito[] = correicaoPorProcesso['padrao'] ?? [];
  readonly correicaoId = signal<string | null>(null);
  readonly jobsPorProcesso = new Map<string, string>();
  readonly linhasPorProcesso = new Map<string, ItemVeredito[]>();
  readonly carregandoCorreicao = signal(false);

  readonly resumoItems = [
    ['Unidade', '1ª Vara Cível'],
    ['Universo', '12.480 processos'],
    ['Regras selecionadas', '8'],
    ['Regra nova', 'RC-017 — Arquivamento com possível pendência'],
    ['Fonte', 'Réplica analítica autorizada'],
    ['Modo', 'Somente leitura'],
    ['Responsável pela aprovação', 'Dra. Helena Moreira'],
    ['Versão do checklist', '1.0 · 8/8/2026'],
  ];

  readonly governancaItems = [
    ['Quem selecionou as regras', 'Marina Alves · 6/8/2026'],
    ['Quem criou a RC-017', 'Dra. Helena Moreira · 7/8/2026'],
    ['Quem revisou', 'Marina Alves · 7/8/2026'],
    ['Quem aprovou', 'Dra. Helena Moreira · 8/8/2026'],
    ['Versão utilizada', 'Checklist 1.0 · RC-017 v1.0'],
    ['Parâmetros aplicados', 'Período 1º/1/2026 a 31/7/2026, exceções ativas'],
  ];

  // Estados reativos (Signals)
  aberto = signal<string | null>(null);
  erroApi = signal<string | null>(null);

  ngOnInit(): void {
    this.route.queryParams.subscribe((params) => {
      const id = params['correicao_id'];
      if (id && id !== this.correicaoId()) {
        this.correicaoId.set(id);
        void this.carregarCorreicao(id);
      }
    });
  }

  private async carregarCorreicao(id: string): Promise<void> {
    this.carregandoCorreicao.set(true);
    this.erroApi.set(null);
    try {
      const lote: CorreicaoStatus = await firstValueFrom(this.processosApi.consultarCorreicao(id));
      const resultados = await Promise.all(lote.jobs.map(async (job) => {
        if (job.status === 'falhou') return { job, resultado: null };
        try { return { job, resultado: await firstValueFrom(this.processosApi.obterResultado(job.job_id)) }; }
        catch { return { job, resultado: null }; }
      }));
      this.jobsPorProcesso.clear();
      this.linhasPorProcesso.clear();
      this.processos = resultados.map(({ job, resultado }) => {
        const numero = this.formatarNumero(job.processo_id);
        this.jobsPorProcesso.set(numero, job.job_id);
        const linhas = (resultado?.respostas ?? []).map((r) => ({
          regra: r.pergunta_id,
          veredito: r.resposta === 'Sim' ? 'Atende' as const : r.resposta === 'Não' ? 'Não atende' as const : 'Não se encaixa' as const,
          trecho: [r.evidencia, r.observacao].filter(Boolean).join(' · ') || 'Sem evidência textual retornada.',
        }));
        this.linhasPorProcesso.set(numero, linhas);
        return {
          numero, unidade: 'Vara selecionada', classe: job.arquivo,
          assunto: 'PDF analisado', situacao: job.status === 'falhou' ? 'Suspenso' : 'Ativo',
          ultimoMovimento: job.error_message ?? this.rotuloStatus(job.status),
          ocorrencias: linhas.filter((l) => l.veredito === 'Não atende').length,
          criticos: 0, atencao: 'Baixa',
        } as Processo;
      });
      this.resumoItems.splice(0, this.resumoItems.length,
        ['Unidade', 'Vara selecionada'], ['PDFs analisados', String(lote.total_processos)],
        ['Regras selecionadas', String(lote.regra_ids.length)], ['Status', lote.status],
        ['Identificador da correição', lote.correicao_id],
      );
    } catch {
      this.erroApi.set('Não foi possível carregar os resultados desta correição.');
    } finally {
      this.carregandoCorreicao.set(false);
    }
  }

  parametrosRevisao(numero: string): Record<string, string> {
    const jobId = this.jobsPorProcesso.get(numero);
    return { processo: numero, ...(jobId ? { job_id: jobId } : {}), ...(this.correicaoId() ? { correicao_id: this.correicaoId()! } : {}) };
  }

  private rotuloStatus(status: JobStatus): string {
    return ({ recebido: 'Na fila', ocr_em_andamento: 'Leitura do PDF', ocr_concluido: 'Leitura concluída', analise_em_andamento: 'Aplicação das regras', concluido: 'Análise concluída', revisao_necessaria: 'Revisão humana necessária', falhou: 'Análise falhou' })[status];
  }

  private formatarNumero(id: string): string {
    return /^\d{20}$/.test(id) ? `${id.slice(0, 7)}-${id.slice(7, 9)}.${id.slice(9, 13)}.${id[13]}.${id.slice(14, 16)}.${id.slice(16)}` : id;
  }

  toggleAberto(numero: string): void {
    this.aberto.update((curr) => (curr === numero ? null : numero));
    this.linhasPadrao = this.linhasPorProcesso.get(numero) ?? correicaoPorProcesso['padrao'] ?? [];
  }

  getVereditoClass(v: Veredito): string {
    const map: Record<Veredito, string> = {
      Atende: 'bg-risk-low-soft text-risk-low',
      'Não atende': 'bg-risk-high-soft text-risk-high',
      'Não se encaixa': 'bg-secondary text-muted-foreground',
    };
    return map[v] || '';
  }
}

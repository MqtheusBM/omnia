import { Component, signal, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { CorreicaoStatus, JobStatus, ProcessosApiService } from '../../services/processos-api.service';

export interface RegraAvaliada {
  id: string;
  nome: string;
  status: 'Conforme' | 'Achado sinalizado';
  duracao: string;
  detalhes: string;
}

export interface EtapaRegra {
  numero: number;
  nome: string;
  status: 'Concluída' | 'Em execução' | 'Pendente';
  detalhe?: string;
}

export interface RegraEmExecucao {
  id: string;
  nome: string;
  descricao: string;
  etapas: EtapaRegra[];
}

export interface RegraPendente {
  id: string;
  nome: string;
  descricao: string;
}

export interface ProcessoEmAnalise {
  numero: string;
  classe: string;
  assunto: string;
  posicao: number;
  totalAmostra: number;
  dataDistribuicao: string;
  ultimaMovimentacao: string;
  regrasAvaliadas: RegraAvaliada[];
  regraAtual: RegraEmExecucao;
  regrasPendentes: RegraPendente[];
}

export interface CorreicaoAtiva {
  id: string;
  unidade: string;
  comarca: string;
  competencia: string;
  totalProcessos: number;
  amostraProcessos: number;
  processosProcessados: number;
  percentualConcluido: number;
  tempoDecorrido: string;
  tempoEstimado: string;
  regrasTotal: number;
  status: 'Em execução' | 'Pausado';
  processoAtual: ProcessoEmAnalise;
}

@Component({
  selector: 'app-acompanhamento',
  standalone: true,
  imports: [CommonModule, RouterLink, AppShellComponent, PanelComponent],
  templateUrl: './acompanhamento.html',
  styleUrl: './acompanhamento.scss',
})
export class AcompanhamentoComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ProcessosApiService);
  private pollingTimer: ReturnType<typeof setInterval> | null = null;
  private discoveryTimer: ReturnType<typeof setInterval> | null = null;
  private elapsedTimer: ReturnType<typeof setInterval> | null = null;

  readonly correicaoId = signal<string | null>(null);
  readonly correicaoAtiva = signal<CorreicaoAtiva | null>(null);
  readonly detalhesProcessoAberto = signal(true);
  readonly carregandoAcompanhamento = signal(true);
  readonly erroApi = signal<string | null>(null);

  private inicioCorreicao: number | null = null;

  ngOnInit(): void {
    this.route.queryParams.subscribe((params) => {
      const id = params['correicao_id'];
      if (id) {
        this.iniciarMonitoramento(id);
      } else {
        void this.descobrirCorreicaoAtiva();
        this.discoveryTimer = setInterval(() => void this.descobrirCorreicaoAtiva(), 5000);
      }
    });
  }

  ngOnDestroy(): void {
    if (this.pollingTimer) clearInterval(this.pollingTimer);
    if (this.discoveryTimer) clearInterval(this.discoveryTimer);
    if (this.elapsedTimer) clearInterval(this.elapsedTimer);
  }

  recarregarAcompanhamento(): void {
    if (this.correicaoId()) void this.atualizarCorreicaoReal();
    else void this.descobrirCorreicaoAtiva();
  }

  private async descobrirCorreicaoAtiva(): Promise<void> {
    if (this.correicaoId()) return;
    this.carregandoAcompanhamento.set(true);
    try {
      const correicoes = await firstValueFrom(this.api.listarCorreicoes());
      const ativa = correicoes.find((item) =>
        item.total_processos > 0 && ['recebida', 'em_andamento'].includes(item.status),
      );
      this.erroApi.set(null);
      if (ativa) {
        this.iniciarMonitoramento(ativa.correicao_id);
      } else {
        this.correicaoAtiva.set(null);
        this.pararCronometro();
      }
    } catch {
      this.erroApi.set('Não foi possível consultar as correições. Verifique se o backend está disponível.');
    } finally {
      this.carregandoAcompanhamento.set(false);
    }
  }

  private iniciarMonitoramento(id: string): void {
    if (this.correicaoId() === id && this.pollingTimer) return;
    const mudouCorreicao = this.correicaoId() !== id;
    this.correicaoId.set(id);
    if (this.discoveryTimer) clearInterval(this.discoveryTimer);
    if (this.pollingTimer) clearInterval(this.pollingTimer);
    if (mudouCorreicao) this.iniciarCronometro(Date.now());
    void this.atualizarCorreicaoReal();
    this.pollingTimer = setInterval(() => void this.atualizarCorreicaoReal(), 2000);
  }

  private async atualizarCorreicaoReal(): Promise<void> {
    const id = this.correicaoId();
    if (!id) return;
    try {
      const dados = await firstValueFrom(this.api.consultarCorreicao(id));
      this.erroApi.set(null);
      if (dados.total_processos === 0 || ['sem_processos', 'interrompida'].includes(dados.status)) {
        this.correicaoAtiva.set(null);
        this.correicaoId.set(null);
        this.pararCronometro();
        if (!this.discoveryTimer) {
          void this.descobrirCorreicaoAtiva();
          this.discoveryTimer = setInterval(() => void this.descobrirCorreicaoAtiva(), 5000);
        }
        return;
      }
      this.aplicarEstadoReal(dados);
      if (['concluida', 'concluida_com_falhas', 'falhou'].includes(dados.status)) {
        if (this.pollingTimer) clearInterval(this.pollingTimer);
        await this.router.navigate(['/aprovacao'], { queryParams: { correicao_id: id } });
      }
    } catch {
      this.erroApi.set('Não foi possível atualizar o acompanhamento. Verifique a conexão com a API.');
    } finally {
      this.carregandoAcompanhamento.set(false);
    }
  }

  private aplicarEstadoReal(dados: CorreicaoStatus): void {
    if (dados.created_at) {
      const dataComFuso = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(dados.created_at)
        ? dados.created_at
        : `${dados.created_at}Z`;
      const inicio = Date.parse(dataComFuso);
      if (Number.isFinite(inicio) && inicio !== this.inicioCorreicao) {
        this.iniciarCronometro(inicio);
      }
    }
    const concluidos = dados.processos_concluidos + dados.processos_falhos;
    const atual = dados.jobs.find((job) => !['concluido', 'revisao_necessaria', 'falhou'].includes(job.status));
    const numeroId = atual?.processo_id ?? dados.jobs.at(-1)?.processo_id ?? '';
    const numero = /^\d{20}$/.test(numeroId)
      ? `${numeroId.slice(0, 7)}-${numeroId.slice(7, 9)}.${numeroId.slice(9, 13)}.${numeroId[13]}.${numeroId.slice(14, 16)}.${numeroId.slice(16)}`
      : numeroId || 'Execução concluída';
    const etapaStatus = (status: JobStatus): EtapaRegra['status'] =>
      ['concluido', 'revisao_necessaria'].includes(status)
        ? 'Concluída'
        : status === 'recebido' ? 'Pendente' : 'Em execução';

    this.correicaoAtiva.set({
      id: dados.correicao_id,
      unidade: dados.unidade ?? this.route.snapshot.queryParamMap.get('unidade') ?? 'Vara selecionada',
      comarca: 'Acervo local',
      competencia: 'Correição',
      totalProcessos: dados.total_processos,
      amostraProcessos: dados.total_processos,
      processosProcessados: concluidos,
      percentualConcluido: dados.total_processos ? Math.round((concluidos / dados.total_processos) * 100) : 0,
      tempoDecorrido: this.formatarTempoDecorrido(),
      tempoEstimado: this.estimarDuracao(dados.total_processos),
      regrasTotal: dados.regra_ids.length,
      status: 'Em execução',
      processoAtual: {
        numero,
        classe: atual?.arquivo ?? 'PDF do acervo',
        assunto: atual ? this.rotuloStatus(atual.status) : 'Execução finalizada',
        posicao: concluidos + (atual ? 1 : 0),
        totalAmostra: dados.total_processos,
        dataDistribuicao: '—',
        ultimaMovimentacao: atual?.error_message ?? this.rotuloStatus(atual?.status ?? 'concluido'),
        regrasAvaliadas: [],
        regraAtual: {
          id: 'ANÁLISE',
          nome: 'Análise documental',
          descricao: 'Etapas informadas pelo processamento do backend.',
          etapas: [
            { numero: 1, nome: 'Leitura e validação do PDF', status: atual ? etapaStatus(atual.status) : 'Concluída' },
            { numero: 2, nome: 'Aplicação das regras selecionadas', status: atual?.status === 'analise_em_andamento' ? 'Em execução' : atual ? 'Pendente' : 'Concluída' },
          ],
        },
        regrasPendentes: [],
      },
    });
  }

  private atualizarTempoDecorrido(): void {
    const ativa = this.correicaoAtiva();
    if (ativa) this.correicaoAtiva.set({ ...ativa, tempoDecorrido: this.formatarTempoDecorrido() });
  }

  private iniciarCronometro(inicio: number): void {
    this.inicioCorreicao = inicio;
    this.atualizarTempoDecorrido();
    if (this.elapsedTimer) clearInterval(this.elapsedTimer);
    this.elapsedTimer = setInterval(() => this.atualizarTempoDecorrido(), 1000);
  }

  private pararCronometro(): void {
    if (this.elapsedTimer) clearInterval(this.elapsedTimer);
    this.elapsedTimer = null;
    this.inicioCorreicao = null;
  }

  private formatarTempoDecorrido(): string {
    if (!this.inicioCorreicao) return '00:00';
    const segundos = Math.max(0, Math.floor((Date.now() - this.inicioCorreicao) / 1000));
    const horas = Math.floor(segundos / 3600);
    const minutos = Math.floor((segundos % 3600) / 60);
    const resto = segundos % 60;
    return horas > 0
      ? `${String(horas).padStart(2, '0')}:${String(minutos).padStart(2, '0')}:${String(resto).padStart(2, '0')}`
      : `${String(minutos).padStart(2, '0')}:${String(resto).padStart(2, '0')}`;
  }

  private estimarDuracao(quantidadePdf: number): string {
    const minimo = quantidadePdf * 3;
    const maximo = quantidadePdf * 5;
    return `${this.formatarDuracao(minimo)}–${this.formatarDuracao(maximo)}`;
  }

  private formatarDuracao(minutos: number): string {
    const horas = Math.floor(minutos / 60);
    const resto = minutos % 60;
    if (horas === 0) return `${resto} min`;
    return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
  }

  private rotuloStatus(status: JobStatus): string {
    const rotulos: Record<JobStatus, string> = {
      recebido: 'Na fila',
      ocr_em_andamento: 'Leitura do PDF',
      ocr_concluido: 'Leitura concluída',
      analise_em_andamento: 'Aplicação das regras',
      concluido: 'Concluído',
      falhou: 'Falhou',
      revisao_necessaria: 'Aguardando revisão',
    };
    return rotulos[status];
  }

  toggleDetalhesProcesso(): void {
    this.detalhesProcessoAberto.update((value) => !value);
  }
}

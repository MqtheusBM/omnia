import { Component, signal, computed, inject, OnInit } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { TagComponent } from '../../components/tag/tag.component';

import {
  unidades,
  RegraBiblioteca,
  Unidade,
} from '../../mock-data/prototype-data';
import { ProcessosApiService, ProcessoCatalogo } from '../../services/processos-api.service';

export interface PacoteRegras {
  id: string;
  nome: string;
  descricao: string;
  regras: string[];
  icone: string;
  destaque?: boolean;
}

@Component({
  selector: 'app-planejamento',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    AppShellComponent,
    PanelComponent,
    TagComponent,
  ],
  templateUrl: './planejamento.component.html',
  styleUrl: './planejamento.component.scss',
})
export class PlanejamentoComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ProcessosApiService);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));

  readonly unidadesLista: Unidade[] = unidades;
  readonly bibliotecaRegras = signal<RegraBiblioteca[]>([]);
  readonly processosCatalogo = signal<ProcessoCatalogo[]>([]);
  readonly carregandoCatalogo = signal(true);
  readonly erroCatalogo = signal<string | null>(null);
  readonly erroExecucao = signal<string | null>(null);
  readonly iniciandoCorreicao = signal(false);
  readonly buscaProcesso = signal('');

  // Pacotes pré-definidos de regras
  readonly pacotesRegras: PacoteRegras[] = [
    {
      id: 'situacao-processual',
      nome: 'Situação processual e cadastro',
      descricao: 'Verifica suspensões, existência de sentença e cadastro de bens apreendidos.',
      regras: ['RC-016', 'RC-017', 'RC-030'],
      icone: 'gavel',
    },
    {
      id: 'prazos-fluxo',
      nome: 'Prazos, movimentação e fluxo cartorário',
      descricao: 'Reúne análise de prazos, juntadas, lançamentos no sistema, paralisação e conclusões antigas.',
      regras: ['RC-020', 'RC-021', 'RC-022', 'RC-028', 'RC-029'],
      icone: 'timer',
    },
    {
      id: 'atos-diligencias',
      nome: 'Remessas, cumprimento e diligências',
      descricao: 'Verifica remessas, repetição de diligências, determinações judiciais, cartas precatórias e atuação do Oficial de Justiça.',
      regras: ['RC-018', 'RC-019', 'RC-024', 'RC-026', 'RC-027'],
      icone: 'task_alt',
    },
    {
      id: 'audiencias-expedientes',
      nome: 'Audiências e expedientes',
      descricao: 'Agrupa identificação em atas, confecção de expedientes e conformidade com as normas da CGJ.',
      regras: ['RC-023', 'RC-025', 'RC-031'],
      icone: 'description',
    },
    {
      id: 'auditoria-completa',
      nome: 'Auditoria Integral',
      descricao: 'Aplica as 16 verificações da tabela informada.',
      regras: Array.from({ length: 16 }, (_, index) => `RC-${String(index + 16).padStart(3, '0')}`),
      icone: 'rule',
      destaque: true,
    },
  ];

  readonly SITUACOES = ['Todas', 'Ativo', 'Suspenso', 'Arquivado'];

  // Estados do Stepper / Fluxo em Etapas
  readonly etapaAtual = signal<number>(1);
  readonly etapasConcluidas = signal<number[]>([]);

  // Etapa 1: Seleção de Unidade
  readonly buscaUnidade = signal<string>('');
  readonly unidadeSelecionada = signal<string>('1ª Vara Cível');

  // Etapa 2: quantidade exata de PDFs a analisar
  readonly quantidadePdf = signal(10);
  readonly modoSelecaoPdf = signal<'automatica' | 'manual'>('automatica');
  readonly processosSelecionadosIds = signal<string[]>([]);
  readonly situacaoFiltro = signal<string>('Todas');
  readonly classeFiltro = signal<string>('');
  readonly assuntoFiltro = signal<string>('');

  // Etapa 3: Seleção de Regras
  readonly modoRegras = signal<'pacotes' | 'individual'>('pacotes');
  readonly pacoteSelecionado = signal<string>('auditoria-completa');
  readonly regrasSelecionadas = signal<string[]>(
    Array.from({ length: 16 }, (_, index) => `RC-${String(index + 16).padStart(3, '0')}`),
  );
  readonly buscaRegra = signal<string>('');

  ngOnInit(): void {
    if (this.isBrowser) void this.carregarCatalogos();
    // Pré-selecionar unidade vinda da URL se houver
    this.route.queryParams.subscribe((params) => {
      if (params['unidade']) {
        const existe = this.unidadesLista.some((u) => u.nome === params['unidade']);
        if (existe) {
          this.unidadeSelecionada.set(params['unidade']);
        }
      }
    });
  }

  private async carregarCatalogos(): Promise<void> {
    this.carregandoCatalogo.set(true);
    try {
      const [processos, regras] = await Promise.all([
        firstValueFrom(this.api.listarProcessos()),
        firstValueFrom(this.api.listarRegras()),
      ]);
      this.processosCatalogo.set(processos);
      this.quantidadePdf.set(Math.min(10, processos.length));
      this.bibliotecaRegras.set(regras);
      this.regrasSelecionadas.set(regras.filter((regra) => regra.selecionada).map((regra) => regra.id));
      this.erroCatalogo.set(null);
    } catch {
      this.erroCatalogo.set('Não foi possível carregar o catálogo de processos e regras. Confira a API e as configurações de acesso ao armazenamento e ao banco.');
    } finally {
      this.carregandoCatalogo.set(false);
    }
  }

  // --- Computed Signals ---

  // Unidade ativa como objeto
  readonly unidadeAtual = computed<Unidade | undefined>(() => {
    return this.unidadesLista.find((u) => u.nome === this.unidadeSelecionada()) || this.unidadesLista[0];
  });

  // Unidades filtradas pela busca na Etapa 1
  readonly unidadesFiltradas = computed<Unidade[]>(() => {
    const termo = this.buscaUnidade().trim().toLowerCase();
    if (!termo) return this.unidadesLista;

    return this.unidadesLista.filter(
      (u) =>
        u.nome.toLowerCase().includes(termo) ||
        u.competencia.toLowerCase().includes(termo) ||
        u.comarca.toLowerCase().includes(termo)
    );
  });

  // Quantidade calculada de processos amostrados
  readonly processosElegiveis = computed(() => {
    const termo = this.buscaProcesso().trim().toLowerCase();
    return this.processosCatalogo().filter(
      (processo) => !termo || processo.numero.toLowerCase().includes(termo),
    );
  });

  readonly processosAmostradosQtd = computed<number>(() => {
    if (this.modoSelecaoPdf() === 'manual') return this.processosSelecionadosIds().length;
    return Math.min(this.quantidadePdf(), this.processosElegiveis().length);
  });

  // Amostra reproduzível: a prévia e o envio usam sempre os mesmos IDs.
  readonly listaProcessosAmostra = computed<ProcessoCatalogo[]>(() => {
    const elegiveis = this.processosElegiveis();
    if (this.modoSelecaoPdf() === 'manual') {
      const selecionados = new Set(this.processosSelecionadosIds());
      return this.processosCatalogo().filter((processo) => selecionados.has(processo.processo_id));
    }
    const semente = this.quantidadePdf();
    return [...elegiveis]
      .sort((a, b) => this.rankAmostra(a.processo_id, semente) - this.rankAmostra(b.processo_id, semente))
      .slice(0, Math.min(this.processosAmostradosQtd(), elegiveis.length));
  });

  // Regras da biblioteca filtradas na Etapa 3
  readonly regrasFiltradas = computed<RegraBiblioteca[]>(() => {
    const b = this.buscaRegra().toLowerCase();
    return this.bibliotecaRegras().filter(
      (r) => r.nome.toLowerCase().includes(b) || r.id.toLowerCase().includes(b)
    );
  });

  // Regras atualmente selecionadas como objetos
  readonly regrasSelecionadasObjetos = computed<RegraBiblioteca[]>(() => {
    return this.bibliotecaRegras().filter((r) =>
      this.regrasSelecionadas().includes(r.id)
    );
  });

  // --- Métodos de Navegação do Stepper ---

  isEtapaConcluida(etapa: number): boolean {
    return this.etapasConcluidas().includes(etapa);
  }

  podeAcessarEtapa(etapa: number): boolean {
    return etapa <= this.etapaAtual() || this.isEtapaConcluida(etapa);
  }

  irParaEtapa(etapa: number): void {
    if (this.podeAcessarEtapa(etapa)) {
      if (etapa < this.etapaAtual()) {
        this.reverterAndamentoPara(etapa);
      }
      this.etapaAtual.set(etapa);
    }
  }

  avancarParaEtapa2(): void {
    if (!this.unidadeSelecionada()) return;
    this.marcarConcluida(1);
    this.etapaAtual.set(2);
  }

  avancarParaEtapa3(): void {
    if (!this.podeIniciarAmostra()) return;
    this.marcarConcluida(2);
    this.etapaAtual.set(3);
  }

  voltarEtapa(): void {
    if (this.etapaAtual() > 1) {
      const novaEtapa = this.etapaAtual() - 1;
      this.reverterAndamentoPara(novaEtapa);
      this.etapaAtual.set(novaEtapa);
    }
  }

  private reverterAndamentoPara(etapa: number): void {
    // Remove do histórico de concluídas todas as etapas a partir da etapa atual de destino
    this.etapasConcluidas.update((lista) => lista.filter((e) => e < etapa));
  }

  private marcarConcluida(etapa: number): void {
    this.etapasConcluidas.update((lista) => {
      return lista.includes(etapa) ? lista : [...lista, etapa];
    });
  }

  // --- Métodos de Seleção ---

  selecionarUnidade(nome: string): void {
    this.unidadeSelecionada.set(nome);
  }

  definirQuantidadePdf(valor: number): void {
    const limite = Math.min(30, this.processosCatalogo().length || 30);
    const quantidade = Math.max(1, Math.min(Math.trunc(valor || 1), limite));
    this.quantidadePdf.set(quantidade);
    this.processosSelecionadosIds.update((ids) => ids.slice(0, quantidade));
  }

  selecionarModoPdf(modo: 'automatica' | 'manual'): void {
    this.modoSelecaoPdf.set(modo);
    if (modo === 'manual') this.processosSelecionadosIds.set([]);
  }

  processoEstaSelecionado(processoId: string): boolean {
    return this.processosSelecionadosIds().includes(processoId);
  }

  alternarProcesso(processoId: string): void {
    this.processosSelecionadosIds.update((ids) => {
      if (ids.includes(processoId)) return ids.filter((id) => id !== processoId);
      if (ids.length >= this.quantidadePdf()) return ids;
      return [...ids, processoId];
    });
  }

  podeIniciarAmostra(): boolean {
    return this.modoSelecaoPdf() === 'automatica'
      ? this.processosAmostradosQtd() > 0
      : this.processosAmostradosQtd() === this.quantidadePdf();
  }

  selecionarModoRegras(modo: 'pacotes' | 'individual'): void {
    this.modoRegras.set(modo);
  }

  selecionarPacote(pacote: PacoteRegras): void {
    this.pacoteSelecionado.set(pacote.id);
    this.regrasSelecionadas.set([...pacote.regras]);
  }

  toggleRegra(id: string): void {
    this.regrasSelecionadas.update((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    );
  }

  selecionarTodasRegras(): void {
    this.regrasSelecionadas.set(this.bibliotecaRegras().map((r) => r.id));
  }

  desmarcarTodasRegras(): void {
    this.regrasSelecionadas.set([]);
  }

  private rankAmostra(id: string, semente: number): number {
    let hash = 2166136261 ^ semente;
    for (const char of id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    return hash >>> 0;
  }

  formatarTamanho(bytes: number): string {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async iniciarCorreicao(): Promise<void> {
    const processosAmostrados = this.listaProcessosAmostra();
    const regras = this.regrasSelecionadas();
    if (!processosAmostrados.length || !this.podeIniciarAmostra() || !regras.length || this.iniciandoCorreicao()) return;

    this.iniciandoCorreicao.set(true);
    this.erroExecucao.set(null);
    try {
      const correicao = await firstValueFrom(this.api.criarCorreicao({
        quantidade_processos: processosAmostrados.length,
        unidade: this.unidadeSelecionada(),
        processo_ids: processosAmostrados.map((processo) => processo.processo_id),
        regra_ids: regras,
      }));
      await this.router.navigate(['/acompanhamento'], {
        queryParams: { correicao_id: correicao.correicao_id, unidade: this.unidadeSelecionada() },
      });
    } catch {
      this.erroExecucao.set('Não foi possível iniciar a correição. Verifique a API, as regras escolhidas e o limite de 30 PDFs por lote.');
    } finally {
      this.iniciandoCorreicao.set(false);
    }
  }
}

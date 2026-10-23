import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../enviroment/environment';

export interface JobCreated {
  job_id: string;
  status: JobStatus;
  processo_id: string | null;
}

export type JobStatus =
  | 'recebido'
  | 'ocr_em_andamento'
  | 'ocr_concluido'
  | 'analise_em_andamento'
  | 'concluido'
  | 'falhou'
  | 'revisao_necessaria';

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  processo_id: string | null;
  total_paginas: number | null;
  error_message: string | null;
}

export interface JobResult {
  job_id: string;
  status: JobStatus;
  total_paginas: number;
  questionario_id: string;
  modelo: string;
  revisao_necessaria: boolean;
  respostas: Array<{
    pergunta_id: string;
    resposta: 'Sim' | 'Não' | 'Não se aplica';
    paginas: number[];
    evidencia: string;
    confianca: 'alta' | 'média' | 'baixa';
    observacao: string | null;
  }>;
  aviso: string;
}

export interface ProcessoCatalogo {
  processo_id: string;
  numero: string;
  arquivo: string;
  tamanho_bytes: number;
  codigo_origem_cnj: string;
}

export interface RegraCorrecional {
  id: string;
  nome: string;
  versao: string;
  uso: string;
  selecionada: boolean;
  descricao: string;
  competencia: string;
  fontes: string;
  autor: string;
  aprovador: string;
  confirmacao: string;
  recomendada: boolean;
}

export interface RegraDraft {
  instrucao: string;
  atende: string;
  nao_atende: string;
  nao_se_encaixa: string;
  ajustes?: string | null;
}

export interface RegraCriada extends RegraCorrecional {
  passos: string[];
}

export interface CorreicaoCreated {
  correicao_id: string;
  status: string;
  total_processos: number;
  quantidade_processos: number;
  unidade?: string | null;
  processo_ids: string[];
  regra_ids: string[];
}

export interface CorreicaoStatus {
  correicao_id: string;
  status: string;
  created_at?: string | null;
  quantidade_processos: number;
  unidade?: string | null;
  total_processos: number;
  processos_concluidos: number;
  processos_falhos: number;
  processo_ids: string[];
  regra_ids: string[];
  jobs: Array<{
    job_id: string;
    processo_id: string;
    arquivo: string;
    status: JobStatus;
    total_paginas: number | null;
    error_message: string | null;
  }>;
}

@Injectable({ providedIn: 'root' })
export class ProcessosApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiUrl.replace(/\/$/, '')}/v1/processos`;

  analisar(file: File): Observable<JobCreated> {
    const data = new FormData();
    data.append('file', file, file.name);
    data.append('questionario_id', 'questionario-exemplo-v1');
    return this.http.post<JobCreated>(`${this.baseUrl}/analisar`, data);
  }

  listarProcessos(): Observable<ProcessoCatalogo[]> {
    return this.http.get<ProcessoCatalogo[]>(`${this.baseUrl}/catalogo`);
  }

  listarRegras(): Observable<RegraCorrecional[]> {
    return this.http.get<RegraCorrecional[]>(`${this.baseUrl}/regras`);
  }

  gerarPassosRegra(payload: RegraDraft): Observable<{ passos: string[] }> {
    return this.http.post<{ passos: string[] }>(`${this.baseUrl}/regras/gerar`, payload);
  }

  salvarRegra(payload: RegraDraft & { nome: string; descricao: string; passos: string[] }): Observable<RegraCriada> {
    return this.http.post<RegraCriada>(`${this.baseUrl}/regras`, payload);
  }

  criarCorreicao(payload: {
    quantidade_processos: number;
    unidade?: string;
    processo_ids: string[];
    regra_ids: string[];
  }): Observable<CorreicaoCreated> {
    return this.http.post<CorreicaoCreated>(`${environment.apiUrl.replace(/\/$/, '')}/v1/correicoes`, payload);
  }

  consultarCorreicao(correicaoId: string): Observable<CorreicaoStatus> {
    return this.http.get<CorreicaoStatus>(
      `${environment.apiUrl.replace(/\/$/, '')}/v1/correicoes/${encodeURIComponent(correicaoId)}`,
    );
  }

  listarCorreicoes(): Observable<CorreicaoStatus[]> {
    return this.http.get<CorreicaoStatus[]>(`${environment.apiUrl.replace(/\/$/, '')}/v1/correicoes`);
  }

  consultarStatus(jobId: string): Observable<JobStatusResponse> {
    return this.http.get<JobStatusResponse>(`${this.baseUrl}/${encodeURIComponent(jobId)}`);
  }

  obterResultado(jobId: string): Observable<JobResult> {
    return this.http.get<JobResult>(
      `${this.baseUrl}/${encodeURIComponent(jobId)}/resultado`,
    );
  }
}

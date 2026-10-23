import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AppShellComponent } from '../../components/app-shell/app-shell.component';
import { PanelComponent } from '../../components/panel/panel.component';
import { CorreicaoStatus, JobResult, ProcessosApiService } from '../../services/processos-api.service';

@Component({
  selector: 'app-correcao',
  standalone: true,
  imports: [CommonModule, RouterLink, AppShellComponent, PanelComponent],
  templateUrl: './correcao.component.html',
})
export class CorrecaoComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ProcessosApiService);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  private timer: ReturnType<typeof setTimeout> | null = null;
  private encerrado = false;

  readonly correicao = signal<CorreicaoStatus | null>(null);
  readonly resultados = signal<Record<string, JobResult>>({});
  readonly erro = signal<string | null>(null);

  ngOnInit(): void {
    if (!this.isBrowser) return;
    this.route.queryParamMap.subscribe((params) => {
      const id = params.get('id');
      if (id) void this.consultar(id);
      else this.erro.set('Identificador da correição não informado.');
    });
  }

  ngOnDestroy(): void {
    this.encerrado = true;
    if (this.timer) clearTimeout(this.timer);
  }

  private async consultar(id: string): Promise<void> {
    if (this.encerrado) return;
    try {
      const status = await firstValueFrom(this.api.consultarCorreicao(id));
      if (this.encerrado) return;
      this.correicao.set(status);
      this.erro.set(null);
      if (['concluida', 'concluida_com_falhas', 'falhou'].includes(status.status)) {
        const prontos = status.jobs.filter((job) => ['concluido', 'revisao_necessaria'].includes(job.status));
        const pares = await Promise.all(prontos.map(async (job) => [
          job.job_id,
          await firstValueFrom(this.api.obterResultado(job.job_id)),
        ] as const));
        this.resultados.set(Object.fromEntries(pares));
      } else {
        this.timer = setTimeout(() => void this.consultar(id), 3000);
      }
    } catch {
      this.erro.set('Não foi possível consultar o andamento. A API ou o banco podem estar indisponíveis.');
      this.timer = setTimeout(() => void this.consultar(id), 5000);
    }
  }

  formatarNumero(processoId: string): string {
    if (!/^\d{20}$/.test(processoId)) return processoId;
    return `${processoId.slice(0, 7)}-${processoId.slice(7, 9)}.${processoId.slice(9, 13)}.${processoId[13]}.${processoId.slice(14, 16)}.${processoId.slice(16)}`;
  }
}

import { Routes } from '@angular/router';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { PlanejamentoComponent } from './pages/planejamento/planejamento.component';
import { ChecklistComponent } from './pages/checklist/checklist.component';
import { AcompanhamentoComponent } from './pages/acompanhamento/acompanhamento';
import { AprovacaoComponent } from './pages/aprovacao/aprovacao.component';
import { AprovacaoProcessoComponent } from './pages/aprovacao-processo/aprovacao-processo.component';
import { ResultadosComponent } from './pages/resultados/resultados.component';
import { CriarRegraComponent } from './pages/criar-regra/criar-regra.component';
import { NotFoundComponent } from './pages/not-found/not-found.component';
import { ParecerEdicaoComponent } from './pages/parecer-edicao/parecer-edicao.component';
import { CorrecaoComponent } from './pages/correcao/correcao.component';

export const routes: Routes = [
  { path: '', component: DashboardComponent },
  { path: 'planejamento', component: PlanejamentoComponent },
  { path: 'checklist', component: ChecklistComponent },
  { path: 'acompanhamento', component: AcompanhamentoComponent },
  { path: 'correcao', component: CorrecaoComponent },
  { path: 'aprovacao', component: AprovacaoComponent },
  { path: 'aprovacao-processo', component: AprovacaoProcessoComponent },
  { path: 'resultados', component: ResultadosComponent },
  { path: 'criar-regra', component: CriarRegraComponent },
  { path: 'parecer-edicao', component: ParecerEdicaoComponent },
  { path: '**', component: NotFoundComponent },
];

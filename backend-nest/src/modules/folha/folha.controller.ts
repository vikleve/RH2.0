import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseIntPipe,
  Post,
  Put,
  Query,
  Req,
  UseGuards,
} from '@nestjs/common';
import { FolhaService } from './folha.service';
import { SessionGuard } from '../auth/session.guard';
import { CsrfGuard } from '../csrf/csrf.guard';

@Controller('folha')
@UseGuards(SessionGuard, CsrfGuard)
export class FolhaController {
  constructor(private readonly service: FolhaService) {}

  @Get()
  async listar(
    @Query('competencia') competencia?: string,
    @Query('colaborador_id') colabId?: string,
    @Query('situacao') situacao?: string,
    @Query('setor') setor?: string,
    @Query('q') q?: string,
  ) {
    const parsedColabId = colabId && /^\d+$/.test(colabId) ? parseInt(colabId, 10) : undefined;
    const folhas = await this.service.listarFolhas({
      competencia,
      colaboradorId: parsedColabId,
      situacao,
      setor,
      termo: q,
    });
    return { sucesso: true, total: folhas.length, dados: folhas };
  }

  @Get(':id')
  async obterPorId(@Param('id', ParseIntPipe) id: number) {
    const folha = await this.service.obterFolhaPorId(id);
    return { sucesso: true, dados: folha };
  }

  @Post()
  @HttpCode(HttpStatus.CREATED)
  async criar(@Body() body: any, @Req() req: any) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const criada = await this.service.criarOuAtualizarFolha(body, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Folha de pagamento calculada e salva com sucesso!',
      dados: criada,
    };
  }

  @Put(':id')
  async atualizar(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: any,
    @Req() req: any,
  ) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    body.folha_id_existente = id;
    const atualizada = await this.service.criarOuAtualizarFolha(body, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Folha de pagamento atualizada com sucesso!',
      dados: atualizada,
    };
  }

  @Post(':id/fechar')
  @HttpCode(HttpStatus.OK)
  async fechar(@Param('id', ParseIntPipe) id: number, @Req() req: any) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const fechada = await this.service.fecharFolha(id, nomeResp);
    return {
      sucesso: true,
      mensagem: `Folha #${id} fechada com sucesso. Edições bloqueadas.`,
      dados: fechada,
    };
  }

  @Post(':id/reabrir')
  @HttpCode(HttpStatus.OK)
  async reabrir(
    @Param('id', ParseIntPipe) id: number,
    @Body('motivo') motivo: string,
    @Req() req: any,
  ) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const reaberta = await this.service.reabrirFolha(id, motivo, nomeResp);
    return {
      sucesso: true,
      mensagem: `Folha #${id} reaberta para edição.`,
      dados: reaberta,
    };
  }

  @Post(':id/calcular')
  async calcular(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: any,
    @Req() req: any,
  ) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    body.folha_id_existente = id;
    const calculada = await this.service.criarOuAtualizarFolha(body, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Folha recalculada com sucesso!',
      dados: calculada,
    };
  }

  @Delete(':id')
  async cancelar(@Param('id', ParseIntPipe) id: number, @Req() req: any) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    await this.service.cancelarFolha(id, nomeResp);
    return {
      sucesso: true,
      mensagem: `Folha #${id} cancelada com sucesso.`,
    };
  }
}


import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseIntPipe,
  Patch,
  Post,
  Put,
  Query,
  Req,
  UseGuards,
} from '@nestjs/common';
import { ColaboradoresService } from './colaboradores.service';
import { SessionGuard } from '../auth/session.guard';
import { CsrfGuard } from '../csrf/csrf.guard';
import { RolesGuard } from '../auth/roles/roles.guard';
import { Roles } from '../auth/roles/roles.decorator';
import { CreateColaboradorDto } from './dto/create-colaborador.dto';
import { UpdateColaboradorDto } from './dto/update-colaborador.dto';

@Controller('colaboradores')
@UseGuards(SessionGuard, CsrfGuard, RolesGuard)
export class ColaboradoresController {
  constructor(private readonly service: ColaboradoresService) {}

  @Get('metricas')
  @Roles('administrador', 'analista_rh', 'operador_dp')
  async obterMetricas() {
    const metricas = await this.service.obterMetricas();
    return { sucesso: true, dados: metricas };
  }

  @Get()
  @Roles('administrador', 'analista_rh', 'operador_dp')
  async listar(
    @Query('q') q?: string,
    @Query('situacao') situacao?: string,
    @Query('setor') setor?: string,
  ) {
    const lista = await this.service.listar({ termo: q, situacao, setor });
    return { sucesso: true, total: lista.length, dados: lista };
  }

  @Get(':id')
  @Roles('administrador', 'analista_rh', 'operador_dp')
  async obterPorId(@Param('id', ParseIntPipe) id: number) {
    const colab = await this.service.obterPorId(id);
    return { sucesso: true, dados: colab };
  }

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @Roles('administrador', 'analista_rh')
  async criar(@Body() body: CreateColaboradorDto, @Req() req: any) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const criado = await this.service.criar(body, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Colaborador cadastrado com sucesso!',
      dados: criado,
    };
  }

  @Put(':id')
  @Roles('administrador', 'analista_rh')
  async atualizar(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: UpdateColaboradorDto,
    @Req() req: any,
  ) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const atualizado = await this.service.atualizar(id, body, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Colaborador atualizado com sucesso!',
      dados: atualizado,
    };
  }

  @Patch(':id/inativar')
  @Roles('administrador', 'analista_rh')
  async inativar(
    @Param('id', ParseIntPipe) id: number,
    @Body('motivo') motivo: string,
    @Req() req: any,
  ) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const dados = await this.service.inativar(id, motivo, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Colaborador inativado com sucesso. Histórico preservado.',
      dados,
    };
  }

  @Patch(':id/reativar')
  @Roles('administrador', 'analista_rh')
  async reativar(@Param('id', ParseIntPipe) id: number, @Req() req: any) {
    const nomeResp = req.user
      ? `${req.user.nome_completo} (${req.user.perfil})`
      : 'Sistema/Administrador';
    const dados = await this.service.reativar(id, nomeResp);
    return {
      sucesso: true,
      mensagem: 'Colaborador reativado com sucesso.',
      dados,
    };
  }

  @Get(':id/historico')
  async obterHistorico(@Param('id', ParseIntPipe) id: number) {
    const hist = await this.service.obterHistorico(id);
    return { sucesso: true, total: hist.length, dados: hist };
  }
}


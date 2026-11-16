import { ForbiddenException, BadRequestException } from '@nestjs/common';
import { ColaboradoresService, EMPRESA_PADRAO_UUID } from './colaboradores.service';
import { ColaboradoresRepository } from './colaboradores.repository';

describe('ColaboradoresService (Unit Tests)', () => {
  let service: ColaboradoresService;
  let repositoryMock: Partial<ColaboradoresRepository>;

  beforeEach(() => {
    repositoryMock = {
      buscarPorId: jest.fn(),
      buscarPorCpf: jest.fn(),
      buscarPorMatricula: jest.fn(),
      listarPaginado: jest.fn(),
      inserir: jest.fn(),
      atualizar: jest.fn(),
      inativar: jest.fn(),
      inserirHistorico: jest.fn(),
      inserirDependentes: jest.fn(),
      buscarHistorico: jest.fn(),
      obterMetricas: jest.fn(),
    };

    service = new ColaboradoresService(repositoryMock as ColaboradoresRepository);
  });

  describe('normalizarCpf e mascararCpf', () => {
    it('deve extrair somente dígitos no normalizarCpf', () => {
      expect(service.normalizarCpf('123.456.789-01')).toBe('12345678901');
      expect(service.normalizarCpf(' 529-982.247/25 ')).toBe('52998224725');
    });

    it('deve mascarar adequadamente o CPF para exibição pública segura', () => {
      expect(service.mascararCpf('52998224725')).toBe('529.***.***-25');
      expect(service.mascararCpf('11144477735')).toBe('111.***.***-35');
      expect(service.mascararCpf('invalido')).toBe('***.***.***-**');
    });
  });

  describe('obterEmpresasAutorizadas', () => {
    it('deve retornar null para administrador irrestrito (acesso global)', () => {
      const admin = { perfil: 'administrador' };
      expect(service.obterEmpresasAutorizadas(admin)).toBeNull();
    });

    it('deve respeitar restrição configurada para administrador com escopo fixo', () => {
      const adminRestrito = {
        perfil: 'administrador',
        empresas_autorizadas: JSON.stringify(['emp-1', 'emp-2']),
      };
      expect(service.obterEmpresasAutorizadas(adminRestrito)).toEqual(['emp-1', 'emp-2']);
    });

    it('deve restringir usuário analista_rh ou operador_dp à sua empresa', () => {
      const analista = { perfil: 'analista_rh', empresa_id: 'empresa-abc-123' };
      expect(service.obterEmpresasAutorizadas(analista)).toEqual(['empresa-abc-123']);
    });

    it('deve usar empresa padrão corporativa se usuário comum não possuir empresa_id', () => {
      const operadorSemEmpresa = { perfil: 'operador_dp' };
      expect(service.obterEmpresasAutorizadas(operadorSemEmpresa)).toEqual([EMPRESA_PADRAO_UUID]);
    });
  });

  describe('validarAcessoEmpresa', () => {
    it('não deve lançar exceção para administrador global', () => {
      expect(() =>
        service.validarAcessoEmpresa('qualquer-empresa', { perfil: 'administrador' }),
      ).not.toThrow();
    });

    it('deve autorizar usuário acessando sua própria empresa', () => {
      const user = { perfil: 'analista_rh', empresa_id: 'minha-empresa' };
      expect(() => service.validarAcessoEmpresa('minha-empresa', user)).not.toThrow();
    });

    it('deve lançar ForbiddenException ao tentar acessar empresa fora do escopo', () => {
      const user = { perfil: 'analista_rh', empresa_id: 'minha-empresa' };
      expect(() => service.validarAcessoEmpresa('outra-empresa', user)).toThrow(
        ForbiddenException,
      );
    });
  });

  describe('validarCriacao', () => {
    it('deve rejeitar payload sem matrícula ou sem nome', () => {
      expect(() =>
        service.validarCriacao({
          matricula: '',
          nomeCompleto: '',
          cpf: '52998224725',
          dataNascimento: '1990-01-01',
        } as any),
      ).toThrow(BadRequestException);
    });

    it('deve rejeitar payload com data de nascimento futura', () => {
      expect(() =>
        service.validarCriacao({
          matricula: 'MAT-01',
          nomeCompleto: 'Fulano',
          cpf: '52998224725',
          dataNascimento: '2099-01-01',
        } as any),
      ).toThrow(BadRequestException);
    });

    it('deve rejeitar admissão anterior à data de nascimento', () => {
      expect(() =>
        service.validarCriacao({
          matricula: 'MAT-01',
          nomeCompleto: 'Fulano',
          cpf: '52998224725',
          dataNascimento: '1990-01-01',
          dataAdmissao: '1985-01-01',
        } as any),
      ).toThrow(BadRequestException);
    });
  });
});

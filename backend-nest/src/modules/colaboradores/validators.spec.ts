import { validarCpf, validarEmail, validarDataIso } from './validators';

describe('Validators — Módulo de Colaboradores', () => {
  describe('validarCpf', () => {
    it('deve aceitar CPFs matematicamente válidos', () => {
      expect(validarCpf('52998224725')).toBe(true);
      expect(validarCpf('529.982.247-25')).toBe(true);
      expect(validarCpf('11144477735')).toBe(true);
      expect(validarCpf('22255588846')).toBe(true);
      expect(validarCpf('84078175031')).toBe(true);
    });

    it('deve rejeitar CPFs com dígitos verificadores incorretos', () => {
      expect(validarCpf('11122233344')).toBe(false);
      expect(validarCpf('52998224700')).toBe(false);
    });

    it('deve rejeitar CPFs formados por 11 números repetidos', () => {
      expect(validarCpf('00000000000')).toBe(false);
      expect(validarCpf('11111111111')).toBe(false);
      expect(validarCpf('99999999999')).toBe(false);
    });

    it('deve rejeitar CPFs vazios ou com tamanho diferente de 11 dígitos', () => {
      expect(validarCpf('')).toBe(false);
      expect(validarCpf('123456789')).toBe(false);
      expect(validarCpf('123456789012')).toBe(false);
    });
  });

  describe('validarEmail', () => {
    it('deve validar e-mails com formato padrão', () => {
      expect(validarEmail('colab@empresa.com.br')).toBe(true);
      expect(validarEmail('nome.sobrenome@sub.dominio.org')).toBe(true);
    });

    it('deve rejeitar formatos de e-mail inválidos', () => {
      expect(validarEmail('')).toBe(false);
      expect(validarEmail('sem_arroba.com')).toBe(false);
      expect(validarEmail('colab@')).toBe(false);
      expect(validarEmail('@dominio.com')).toBe(false);
    });
  });

  describe('validarDataIso', () => {
    it('deve validar datas no formato ISO AAAA-MM-DD', () => {
      expect(validarDataIso('1990-05-15')).toBe(true);
      expect(validarDataIso('2024-02-29')).toBe(true); // Ano bissexto
      expect(validarDataIso('2000-12-31')).toBe(true);
    });

    it('deve rejeitar datas fora do calendário ou com formato inválido', () => {
      expect(validarDataIso('')).toBe(false);
      expect(validarDataIso('2023-02-29')).toBe(false); // 2023 não é bissexto
      expect(validarDataIso('15/05/1990')).toBe(false);
      expect(validarDataIso('2020-13-01')).toBe(false);
      expect(validarDataIso('texto-aleatorio')).toBe(false);
    });
  });
});

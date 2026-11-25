# -*- coding: utf-8 -*-
"""Exceções compartilhadas da Plataforma de Gestão do Ciclo Trabalhista."""


class PlataformaValidacaoException(Exception):
    """Exceção para violações de validação ou regras de negócio (HTTP 400)."""


class PlataformaAcessoNegadoException(Exception):
    """Exceção para permissão ou segregação de funções violada (HTTP 403)."""


class PlataformaRecursoNaoEncontradoException(Exception):
    """Exceção para recurso inexistente (HTTP 404)."""

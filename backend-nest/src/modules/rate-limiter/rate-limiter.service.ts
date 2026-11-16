import { Injectable } from '@nestjs/common';

@Injectable()
export class RateLimiterService {
  private readonly maxTentativas = 5;
  private readonly janelaSegundos = 900; // 15 minutos
  private tentativas: Map<string, number[]> = new Map();

  private limparAntigas(chave: string, agora: number) {
    const corte = agora - this.janelaSegundos;
    const lista = this.tentativas.get(chave) || [];
    const filtrada = lista.filter((t) => t > corte);
    if (filtrada.length > 0) {
      this.tentativas.set(chave, filtrada);
    } else {
      this.tentativas.delete(chave);
    }
  }

  estaBloqueado(chave: string): { bloqueado: boolean; restante: number } {
    if (!chave) return { bloqueado: false, restante: 0 };
    const agora = Date.now() / 1000;
    this.limparAntigas(chave, agora);

    const lista = this.tentativas.get(chave) || [];
    if (lista.length >= this.maxTentativas) {
      const maisAntiga = lista[0];
      const restante = Math.max(1, Math.floor(this.janelaSegundos - (agora - maisAntiga)));
      return { bloqueado: true, restante };
    }
    return { bloqueado: false, restante: 0 };
  }

  registrarFalha(chave: string): { bloqueado: boolean; restante: number } {
    if (!chave) return { bloqueado: false, restante: 0 };
    const agora = Date.now() / 1000;
    this.limparAntigas(chave, agora);

    const lista = this.tentativas.get(chave) || [];
    lista.push(agora);
    this.tentativas.set(chave, lista);

    if (lista.length >= this.maxTentativas) {
      const maisAntiga = lista[0];
      const restante = Math.max(1, Math.floor(this.janelaSegundos - (agora - maisAntiga)));
      return { bloqueado: true, restante };
    }
    return { bloqueado: false, restante: 0 };
  }

  registrarSucesso(chave: string): void {
    if (chave) {
      this.tentativas.delete(chave);
    }
  }

  resetar(): void {
    this.tentativas.clear();
  }
}


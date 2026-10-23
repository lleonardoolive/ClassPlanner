from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ================= CAMINHOS ABSOLUTOS =================
BASE_DIR = Path(__file__).parent.resolve()
ARQUIVO_CONFIGURACAO = BASE_DIR / "configuracoes_calendario.json"
ARQUIVO_AGENDA_JSON_ANTIGO = BASE_DIR / "agenda_aulas.json"
BANCO_DADOS_AULAS = BASE_DIR / "banco_aulas.db"

# ================= ENUMS E DATACLASSES =================
class CategoriaAula(Enum):
    TEORICA = "Teórica"
    LUDICA = "Lúdica"
    PRATICA = "Prática"
    AVALIACAO = "Avaliação"
    REVISAO = "Revisão"
    PASSEIO_CULTURA = "Passeio e Cultura"
    OUTRA = "Outra"

class TipoEvento(Enum):
    FERIADO = "Feriado"
    RECESSO = "Recesso"
    SABADO_LETIVO = "Sábado Letivo"
    INICIO_ANO = "Início do Ano Letivo"
    FIM_ANO = "Fim do Ano Letivo"

class TipoAvaliacao(Enum):
    PARCIAL = "Avaliação Parcial"
    TRIMESTRAL = "Avaliação Trimestral"
    TRABALHO = "Trabalho Trimestral"
    ATIVIDADE = "Atividade Avaliativa"

@dataclass
class Aula:
    id: str
    data: str
    turma: str
    disciplina: str
    categoria: str
    bncc: str = ""
    nome_local: str = ""
    endereco_local: str = ""
    email_local: str = ""
    telefone_local: str = ""
    observacoes: str = ""
    autorizacao_pais: bool = False
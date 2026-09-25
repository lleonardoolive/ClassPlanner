import sqlite3
from models import Aula

class RepositorioAulas:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._criar_tabelas()

    def _criar_tabelas(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS aulas (
                    id TEXT PRIMARY KEY,
                    data TEXT,
                    turma TEXT,
                    disciplina TEXT,
                    categoria TEXT,
                    bncc TEXT,
                    nome_local TEXT,
                    endereco_local TEXT,
                    observacoes TEXT,
                    autorizacao_pais INTEGER
                )
            ''')
            try:
                self.conn.execute('ALTER TABLE aulas ADD COLUMN email_local TEXT DEFAULT ""')
                self.conn.execute('ALTER TABLE aulas ADD COLUMN telefone_local TEXT DEFAULT ""')
            except sqlite3.OperationalError:
                pass 

    def listar_todas(self) -> list[Aula]:
        cursor = self.conn.execute('SELECT * FROM aulas ORDER BY data ASC')
        return [self._linha_para_aula(row) for row in cursor.fetchall()]

    def salvar(self, aula: Aula):
        with self.conn:
            self.conn.execute('''
                INSERT INTO aulas (id, data, turma, disciplina, categoria, bncc, nome_local, endereco_local, email_local, telefone_local, observacoes, autorizacao_pais)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data=excluded.data, turma=excluded.turma, disciplina=excluded.disciplina,
                    categoria=excluded.categoria, bncc=excluded.bncc, nome_local=excluded.nome_local,
                    endereco_local=excluded.endereco_local, email_local=excluded.email_local,
                    telefone_local=excluded.telefone_local, observacoes=excluded.observacoes,
                    autorizacao_pais=excluded.autorizacao_pais
            ''', (aula.id, aula.data, aula.turma, aula.disciplina, aula.categoria, aula.bncc, 
                  aula.nome_local, aula.endereco_local, aula.email_local, aula.telefone_local, aula.observacoes, int(aula.autorizacao_pais)))

    def excluir(self, aula_id: str):
        with self.conn:
            self.conn.execute('DELETE FROM aulas WHERE id = ?', (aula_id,))

    def excluir_multiplos(self, aulas_ids: list[str]):
        """Exclui múltiplas aulas de uma só vez."""
        with self.conn:
            self.conn.executemany('DELETE FROM aulas WHERE id = ?', [(i,) for i in aulas_ids])

    def excluir_por_ano(self, ano: str):
        """Limpa todas as aulas cadastradas em um determinado ano letivo."""
        with self.conn:
            self.conn.execute("DELETE FROM aulas WHERE data LIKE ?", (f"{ano}-%",))

    def fechar_conexao(self):
        self.conn.close()

    def _linha_para_aula(self, row) -> Aula:
        return Aula(
            id=row['id'], data=row['data'], turma=row['turma'], disciplina=row['disciplina'],
            categoria=row['categoria'], bncc=row['bncc'], nome_local=row['nome_local'],
            endereco_local=row['endereco_local'], email_local=row['email_local'],
            telefone_local=row['telefone_local'], observacoes=row['observacoes'],
            autorizacao_pais=bool(row['autorizacao_pais'])
        )
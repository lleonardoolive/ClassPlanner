import json
import os
import sqlite3
import uuid
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkcalendar import Calendar, DateEntry
except ImportError as exc:
    raise SystemExit("Instale a biblioteca 'tkcalendar' antes de executar: pip3 install tkcalendar") from exc

# ================= CAMINHOS ABSOLUTOS E LOGS =================
BASE_DIR = Path(__file__).parent.resolve()
ARQUIVO_CONFIGURACAO = BASE_DIR / "configuracoes_calendario.json"
ARQUIVO_AGENDA_JSON_ANTIGO = BASE_DIR / "agenda_aulas.json"
BANCO_DADOS_AULAS = BASE_DIR / "banco_aulas.db"

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

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


# ================= CAMADA MODEL (BANCO DE DADOS) =================
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
            # Migração automática para proteger os dados de bancos já existentes
            try:
                self.conn.execute('ALTER TABLE aulas ADD COLUMN email_local TEXT DEFAULT ""')
                self.conn.execute('ALTER TABLE aulas ADD COLUMN telefone_local TEXT DEFAULT ""')
            except sqlite3.OperationalError:
                pass # As colunas já existem

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


# ================= CAMADA SERVICE (LÓGICA DE NEGÓCIO) =================
class ServicoAulas:
    def __init__(self, bd: RepositorioAulas):
        self.bd = bd

    def marcar_como_avaliacao(self, data_str: str, turma: str, disciplina: str, tipo_avaliacao: str) -> bool:
        aulas = self.bd.listar_todas()
        aula_alvo = next((a for a in aulas if a.data == data_str and a.turma == turma and a.disciplina == disciplina), None)
        
        if not aula_alvo:
            return False 
            
        aula_alvo.categoria = CategoriaAula.AVALIACAO.value
        obs_atual = aula_alvo.observacoes.replace("Gerada automaticamente.", "").strip()
        aula_alvo.observacoes = f"[{tipo_avaliacao}]\n{obs_atual}".strip()
        
        self.bd.salvar(aula_alvo)
        return True

    def exportar_ics(self, aulas: list[Aula], caminho: str):
        if not aulas:
            raise ValueError("Não há aulas no banco para exportar.")
            
        # Função interna para limpar caracteres que quebram o arquivo .ics
        def _escapar_ics(texto: str) -> str:
            if not texto: return ""
            return texto.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
            
        linhas = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Planejador de Aulas by Leonardo O.//BR",
            "CALSCALE:GREGORIAN"
        ]
        
        for aula in aulas:
            try:
                data_obj = datetime.strptime(aula.data, "%Y-%m-%d")
                dt_str = data_obj.strftime("%Y%m%d")
                linhas.append("BEGIN:VEVENT")
                linhas.append(f"UID:{aula.id}@planejador.com")
                linhas.append(f"DTSTART;TZID=America/Sao_Paulo:{dt_str}T080000")
                linhas.append(f"DTEND;TZID=America/Sao_Paulo:{dt_str}T090000")
                
                titulo = f"{aula.disciplina} ({aula.turma}) - {aula.categoria}"
                linhas.append(f"SUMMARY:{_escapar_ics(titulo)}")
                
                desc = f"BNCC: {aula.bncc}\n\n{aula.observacoes}"
                linhas.append(f"DESCRIPTION:{_escapar_ics(desc)}")
                
                if aula.categoria == CategoriaAula.PASSEIO_CULTURA.value:
                    loc = f"{aula.endereco_local} - {aula.nome_local}"
                    linhas.append(f"LOCATION:{_escapar_ics(loc)}")
                    
                linhas.append("END:VEVENT")
            except ValueError as e:
                logging.warning(f"Data inválida ignorada na geração do ICS ({aula.data}): {e}")
                
        linhas.append("END:VCALENDAR")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))

    def gerar_grade_automatica(self, turma: str, disc: str, dias_selecionados: list[int], eventos_especiais: list[dict]) -> tuple[int, str]:
        inicio_ano = next((e["data"] for e in eventos_especiais if e["tipo"] == TipoEvento.INICIO_ANO.value), None)
        fim_ano = next((e["data"] for e in eventos_especiais if e["tipo"] == TipoEvento.FIM_ANO.value), None)

        if not inicio_ano or not fim_ano:
            return 0, "Marcos do ano letivo não definidos. Vá em Configurações e adicione eventos de 'Início do Ano Letivo' e 'Fim do Ano Letivo'."

        data_inicio = datetime.strptime(inicio_ano, "%Y-%m-%d").date()
        data_fim = datetime.strptime(fim_ano, "%Y-%m-%d").date()

        if data_inicio > data_fim:
             return 0, "A data de início do ano letivo deve ser anterior à data de fim."

        aulas_geradas = 0
        dias_bloqueados = [e["data"] for e in eventos_especiais if e["tipo"] in [TipoEvento.FERIADO.value, TipoEvento.RECESSO.value]]
        aulas_existentes = self.bd.listar_todas()
        
        data_alvo = data_inicio
        while data_alvo <= data_fim:
            data_str = data_alvo.strftime("%Y-%m-%d")
            
            if data_alvo.weekday() in dias_selecionados and data_str not in dias_bloqueados:
                existe = any(a.data == data_str and a.turma == turma and a.disciplina == disc for a in aulas_existentes)
                if not existe:
                    nova_aula = Aula(
                        id=uuid.uuid4().hex, data=data_str, turma=turma, disciplina=disc,
                        categoria=CategoriaAula.TEORICA.value, bncc="", observacoes="Gerada automaticamente."
                    )
                    self.bd.salvar(nova_aula)
                    aulas_existentes.append(nova_aula)
                    aulas_geradas += 1
            data_alvo += timedelta(days=1)
            
        return aulas_geradas, "Sucesso"

    def exportar_pdf(self, aula: Aula, caminho: str):
        texto = f"Plano de Aula: {aula.data}\nTurma: {aula.turma} | Disciplina: {aula.disciplina}\nBNCC: {aula.bncc}\n\nObs:\n{aula.observacoes}"
        try:
            from reportlab.pdfgen import canvas
            pdf = canvas.Canvas(caminho)
            pdf.drawString(50, 800, f"Plano de Aula: {aula.data}")
            y = 770
            for linha in texto.splitlines():
                pdf.drawString(50, y, linha[:100])
                y -= 20
            pdf.save()
        except ImportError:
            logging.warning("Biblioteca ReportLab não encontrada. Salvando como .txt.")
            with open(caminho.replace('.pdf','.txt'), "w", encoding="utf-8") as f: 
                f.write(texto)


# ================= MODAL DE AVALIAÇÕES (NOVA VIEW) =================
class JanelaAvaliacoes(tk.Toplevel):
    def __init__(self, parent, servico, turma, disciplina):
        super().__init__(parent)
        self.title(f"Agendar Avaliações - {turma} ({disciplina})")
        self.geometry("550x570")
        self.configure(bg="#F8FAFC")
        self.resizable(False, False)
        
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))
        
        self.servico = servico
        self.turma = turma
        self.disciplina = disciplina
        self.parent_app = parent 
        
        self._construir_interface()

    def _construir_interface(self):
        ttk.Label(self, text="Selecione o dia letivo gerado para marcá-lo como Avaliação:", font=("Inter", 11, "bold"), background="#F8FAFC", foreground="#1E293B").pack(pady=(20, 10))
        
        self.cal = Calendar(self, selectmode="day", date_pattern="yyyy-mm-dd", font=("Inter", 10),
                            background="white", foreground="#1E293B", bordercolor="#E2E8F0",
                            headersbackground="#F1F5F9", headersforeground="#475569", 
                            selectbackground="#DC2626", selectforeground="white") 
        self.cal.pack(fill="x", padx=30, pady=10)
        
        frame_controles = ttk.Frame(self, style="Card.TFrame", padding=15)
        frame_controles.pack(fill="x", padx=30, pady=10)
        
        ttk.Label(frame_controles, text="Tipo:", background="#ffffff").pack(side="left", padx=5)
        self.combo_tipo = ttk.Combobox(frame_controles, values=[t.value for t in TipoAvaliacao], state="readonly", width=23, font=("Inter", 10))
        self.combo_tipo.set(TipoAvaliacao.PARCIAL.value)
        self.combo_tipo.pack(side="left", padx=5)
        
        ttk.Button(frame_controles, text="📌 Converter Aula", style="Primary.TButton", command=self._registrar_avaliacao).pack(side="right", padx=5)
        
        ttk.Label(self, text="Histórico de Registros:", font=("Inter", 10, "bold"), background="#F8FAFC").pack(anchor="w", padx=30, pady=(10, 0))
        self.lista_feedback = tk.Listbox(self, font=("Consolas", 10), height=5, relief="flat", highlightbackground="#E2E8F0", highlightthickness=1)
        self.lista_feedback.pack(fill="x", padx=30, pady=5)
        
        ttk.Button(self, text="✅ Concluir e Fechar", style="Success.TButton", command=self._fechar).pack(pady=15)

    def _registrar_avaliacao(self):
        data_sel = self.cal.get_date()
        tipo = self.combo_tipo.get()
        
        sucesso = self.servico.marcar_como_avaliacao(data_sel, self.turma, self.disciplina, tipo)
        
        if sucesso:
            data_br = datetime.strptime(data_sel, "%Y-%m-%d").strftime("%d/%m/%Y")
            self.lista_feedback.insert(tk.END, f"[{data_br}] {tipo} definida!")
            self.lista_feedback.yview(tk.END)
        else:
            messagebox.showwarning("Aviso", "Não há aula teórica desta turma/disciplina na data selecionada para converter. Escolha um dia letivo válido.", parent=self)

    def _fechar(self):
        self.parent_app._recarregar_dados_banco() 
        self.parent_app.notebook.select(self.parent_app.aba_agenda)
        self.destroy()


# ================= CAMADA VIEW PRINCIPAL (TKINTER) =================
class PlanejadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Planejador de Aulas - Dashboard do Professor")
        self.geometry("1400x850")
        self.minsize(1200, 750)
        
        self.fonte_padrao = ("Inter", 11)
        self.fonte_titulo = ("Inter", 14, "bold")
        self.fonte_codigo = ("Consolas", 11)
        
        self._aplicar_tema_moderno()
        
        self.bd = RepositorioAulas(BANCO_DADOS_AULAS)
        self.servico = ServicoAulas(self.bd)
        
        self.protocol("WM_DELETE_WINDOW", self._encerrar_aplicacao)
        self._migrar_json_antigo()
        self.aulas_registradas = self.bd.listar_todas()
        
        self.config_dados = self._carregar_configuracoes()
        self.eventos_especiais = self.config_dados.get("eventos", [])
        self.turmas_cadastradas = self.config_dados.get("turmas", ["6º Ano A", "7º Ano A", "8º Ano A", "9º Ano A"])
        self.disciplinas_cadastradas = self.config_dados.get("disciplinas", ["Inglês", "Artes"])
        
        self.aula_em_edicao = None
        self.filtro_mes_atual = tk.BooleanVar(value=True)
        
        self._criar_interface()
        self._marcar_calendario()

    def _encerrar_aplicacao(self):
        logging.info("Encerrando aplicação e salvando SQLite...")
        self.bd.fechar_conexao()
        self.destroy()

    def _aplicar_tema_moderno(self):
        self.configure(bg="#F8FAFC")
        style = ttk.Style(self)
        style.theme_use('clam')
        
        cor_fundo, cor_card, cor_texto_principal = "#F8FAFC", "#FFFFFF", "#1E293B"
        cor_primaria, cor_sucesso, cor_aviso, cor_perigo = "#2563EB", "#10B981", "#F59E0B", "#EF4444"
        
        style.configure(".", background=cor_fundo, foreground=cor_texto_principal, font=self.fonte_padrao)
        style.configure("TNotebook", background=cor_fundo, borderwidth=0)
        style.configure("TNotebook.Tab", padding=[25, 12], font=("Inter", 11, "bold"), background="#E2E8F0", borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", cor_primaria), ("active", "#CBD5E1")], foreground=[("selected", "white")])
        
        style.configure("Card.TFrame", background=cor_card, relief="flat", borderwidth=1, bordercolor="#E2E8F0")
        style.configure("TLabelframe", background=cor_card, font=("Inter", 12, "bold"), borderwidth=1)
        style.configure("TLabelframe.Label", background=cor_card, foreground=cor_primaria, padding=[10, 5])
        
        style.configure("TButton", font=("Inter", 11), padding=[15, 8], borderwidth=0, relief="flat")
        style.configure("Primary.TButton", background=cor_primaria, foreground="white")
        style.map("Primary.TButton", background=[("active", "#1D4ED8")])
        style.configure("Success.TButton", background=cor_sucesso, foreground="white")
        style.map("Success.TButton", background=[("active", "#059669")])
        style.configure("Warning.TButton", background=cor_aviso, foreground="white")
        style.map("Warning.TButton", background=[("active", "#D97706")])
        style.configure("Danger.TButton", background=cor_perigo, foreground="white")
        style.map("Danger.TButton", background=[("active", "#B91C1C")])
        
        style.configure("Treeview", font=self.fonte_padrao, background=cor_card, foreground=cor_texto_principal, rowheight=35, borderwidth=0)
        style.configure("Treeview.Heading", font=("Inter", 11, "bold"), background="#F1F5F9", foreground="#475569", padding=[5, 10], borderwidth=0)
        style.map("Treeview", background=[('selected', '#DBEAFE')], foreground=[('selected', '#1E3A8A')])

    def _migrar_json_antigo(self):
        if ARQUIVO_AGENDA_JSON_ANTIGO.exists():
            try:
                with ARQUIVO_AGENDA_JSON_ANTIGO.open("r", encoding="utf-8") as f:
                    dados = json.load(f)
                for item in dados:
                    aula = Aula(
                        id=item.get("id", uuid.uuid4().hex),
                        data=item.get("data", "2026-01-01"),
                        turma=item.get("turma", ""),
                        disciplina=item.get("disciplina", ""),
                        categoria=item.get("categoria", CategoriaAula.TEORICA.value),
                        bncc=item.get("bncc", ""),
                        nome_local=item.get("nome_local", ""),
                        endereco_local=item.get("endereco_local", ""),
                        email_local=item.get("email_local", ""),
                        telefone_local=item.get("telefone_local", ""),
                        observacoes=item.get("observacoes", ""),
                        autorizacao_pais=item.get("autorizacao_pais", False)
                    )
                    self.bd.salvar(aula)
                os.rename(ARQUIVO_AGENDA_JSON_ANTIGO, str(ARQUIVO_AGENDA_JSON_ANTIGO) + ".bkp")
                messagebox.showinfo("Migração Concluída", "JSON migrado pro SQLite com sucesso!")
            except Exception as e:
                logging.error(f"Falha na migração: {e}")

    def _criar_interface(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=25, pady=25)
        
        self.aba_agenda = ttk.Frame(self.notebook)
        self.aba_editor = ttk.Frame(self.notebook)
        self.aba_grade = ttk.Frame(self.notebook)
        self.aba_config = ttk.Frame(self.notebook)
        
        self.notebook.add(self.aba_agenda, text="📅 Agenda Geral")
        self.notebook.add(self.aba_editor, text="📝 Editor de Aula")
        self.notebook.add(self.aba_grade, text="⚡ Gerador de Grade")
        self.notebook.add(self.aba_config, text="⚙️ Configurações")
        
        self._construir_aba_agenda()
        self._construir_aba_editor()
        self._construir_aba_grade()
        self._construir_aba_config()

    def _construir_aba_agenda(self):
        pane = ttk.PanedWindow(self.aba_agenda, orient=tk.HORIZONTAL)
        pane.pack(fill="both", expand=True, pady=15)
        
        frame_cal = ttk.Frame(pane, style="Card.TFrame", padding=20)
        pane.add(frame_cal, weight=1)
        ttk.Label(frame_cal, text="Selecione uma data", font=self.fonte_titulo, background="#ffffff").pack(anchor="w", pady=(0,15))
        
        self.cal = Calendar(frame_cal, selectmode="day", date_pattern="yyyy-mm-dd", font=self.fonte_padrao, 
                            background="white", foreground="#1E293B", bordercolor="#E2E8F0",
                            headersbackground="#F1F5F9", headersforeground="#475569", 
                            selectbackground="#2563EB", selectforeground="white",
                            normalbackground="white", weekendbackground="#F8FAFC",
                            showweeknumbers=False)
        self.cal.pack(fill="x", expand=False)
        self.cal.bind("<<CalendarSelected>>", self._ao_selecionar_data_calendario)
        
        self.frame_resumo = ttk.LabelFrame(frame_cal, text="Detalhes do Dia", padding=15)
        self.frame_resumo.pack(fill="both", expand=True, pady=20)
        self.lbl_resumo_dia = ttk.Label(self.frame_resumo, text="...", font=self.fonte_padrao, background="#ffffff", wraplength=350, justify="left")
        self.lbl_resumo_dia.pack(anchor="nw")

        frame_lista = ttk.Frame(pane, style="Card.TFrame", padding=20)
        pane.add(frame_lista, weight=3)
        
        cabecalho_lista = tk.Frame(frame_lista, background="#ffffff")
        cabecalho_lista.pack(fill="x", pady=(0,15))
        ttk.Label(cabecalho_lista, text="Aulas Planejadas", font=self.fonte_titulo, background="#ffffff").pack(side="left")
        ttk.Checkbutton(cabecalho_lista, text="Mostrar apenas este mês", variable=self.filtro_mes_atual, command=self._atualizar_lista, style="TCheckbutton").pack(side="right")

        self.tree_aulas = ttk.Treeview(frame_lista, columns=("Data", "Turma", "Disciplina", "Categoria", "BNCC"), show="headings")
        colunas = [("Data", 100), ("Turma", 120), ("Disciplina", 150), ("Categoria", 150), ("BNCC", 120)]
        for col, width in colunas:
            self.tree_aulas.heading(col, text=col, command=lambda c=col: self._ordenar_treeview(c, False))
            self.tree_aulas.column(col, width=width, anchor="center" if col == "Data" else "w")
            
        self.tree_aulas.pack(fill="both", expand=True, side="left")
        
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=self.tree_aulas.yview)
        scroll.pack(side="right", fill="y")
        self.tree_aulas.config(yscrollcommand=scroll.set)
        
        # Tags de Cor no Treeview
        self.tree_aulas.tag_configure(CategoriaAula.TEORICA.value, foreground="#1E293B")
        self.tree_aulas.tag_configure(CategoriaAula.LUDICA.value, foreground="#8B5CF6")
        self.tree_aulas.tag_configure(CategoriaAula.PRATICA.value, foreground="#059669")
        self.tree_aulas.tag_configure(CategoriaAula.AVALIACAO.value, foreground="#DC2626", font=("Inter", 11, "bold"))
        self.tree_aulas.tag_configure(CategoriaAula.REVISAO.value, foreground="#D97706")
        self.tree_aulas.tag_configure(CategoriaAula.PASSEIO_CULTURA.value, foreground="#2563EB", font=("Inter", 11, "bold"))
        
        frame_botoes = ttk.Frame(self.aba_agenda)
        frame_botoes.pack(fill="x", pady=10)
        
        ttk.Button(frame_botoes, text="➕ Nova", style="Primary.TButton", command=self._nova_aula_pelo_calendario).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="✏️ Editar", command=self._editar_aula_selecionada).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="🐑 Clonar", style="Warning.TButton", command=self._clonar_aula).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="🗑️ Excluir", style="Danger.TButton", command=self._excluir_aula).pack(side="left", padx=5)
        
        ttk.Button(frame_botoes, text="☁️ Exportar .ics", style="Success.TButton", command=self._exportar_google_calendar).pack(side="right", padx=5)
        ttk.Button(frame_botoes, text="📄 Gerar PDF", command=self._exportar_pdf).pack(side="right", padx=5)
        
        self._atualizar_lista()

    def _ordenar_treeview(self, col, reverse):
        l = [(self.tree_aulas.set(k, col), k) for k in self.tree_aulas.get_children('')]
        if col == "Data":
            l.sort(key=lambda t: datetime.strptime(t[0], "%d/%m/%Y"), reverse=reverse)
        else:
            l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l): self.tree_aulas.move(k, '', index)
        self.tree_aulas.heading(col, command=lambda: self._ordenar_treeview(col, not reverse))

    def _construir_aba_editor(self):
        container = ttk.Frame(self.aba_editor, padding=30)
        container.pack(fill="both", expand=True)
        
        form_frame = ttk.LabelFrame(container, text="Detalhes do Planejamento", padding=35)
        form_frame.pack(fill="both", expand=True)
        
        self.campos = {}
        fonte_input = ("Inter", 11)
        
        ttk.Label(form_frame, text="Data:", background="#ffffff").grid(row=0, column=0, sticky="w", pady=15)
        self.campos['data'] = DateEntry(form_frame, width=15, background='#2563EB', foreground='white', borderwidth=0, date_pattern="yyyy-mm-dd", font=fonte_input)
        self.campos['data'].grid(row=0, column=1, sticky="w", padx=15)
        
        ttk.Label(form_frame, text="Turma:", background="#ffffff").grid(row=1, column=0, sticky="w", pady=15)
        self.campos['turma'] = ttk.Combobox(form_frame, values=self.turmas_cadastradas, width=28, font=fonte_input)
        self.campos['turma'].grid(row=1, column=1, sticky="w", padx=15)

        ttk.Label(form_frame, text="Disciplina:", background="#ffffff").grid(row=1, column=2, sticky="w", pady=15, padx=(20,0))
        self.campos['disciplina'] = ttk.Combobox(form_frame, values=self.disciplinas_cadastradas, width=28, font=fonte_input)
        self.campos['disciplina'].grid(row=1, column=3, sticky="w", padx=15)
        self.campos['disciplina'].bind("<<ComboboxSelected>>", self._atualizar_dropdown_bncc)

        ttk.Label(form_frame, text="Categoria:", background="#ffffff").grid(row=2, column=0, sticky="w", pady=15)
        self.campos['categoria'] = ttk.Combobox(form_frame, values=[c.value for c in CategoriaAula], state="readonly", width=28, font=fonte_input)
        self.campos['categoria'].set(CategoriaAula.TEORICA.value)
        self.campos['categoria'].grid(row=2, column=1, sticky="w", padx=15)
        self.campos['categoria'].bind("<<ComboboxSelected>>", self._toggle_campos_passeio)

        ttk.Label(form_frame, text="Cód. BNCC:", background="#ffffff").grid(row=2, column=2, sticky="w", pady=15, padx=(20,0))
        self.campos['bncc'] = ttk.Combobox(form_frame, values=[], width=28, font=fonte_input)
        self.campos['bncc'].grid(row=2, column=3, sticky="w", padx=15)

        self.frame_passeio = ttk.Frame(form_frame, style="Card.TFrame", padding=15)
        self.frame_passeio.grid(row=3, column=0, columnspan=4, sticky="ew", pady=15)
        self.frame_passeio.grid_remove()

        ttk.Label(self.frame_passeio, text="Local:", background="#ffffff").grid(row=0, column=0, sticky="w")
        self.campos['nome_local'] = ttk.Entry(self.frame_passeio, width=28, font=fonte_input)
        self.campos['nome_local'].grid(row=0, column=1, padx=15)
        
        ttk.Label(self.frame_passeio, text="Endereço:", background="#ffffff").grid(row=0, column=2, sticky="w", padx=(20,0))
        self.campos['endereco_local'] = ttk.Entry(self.frame_passeio, width=38, font=fonte_input)
        self.campos['endereco_local'].grid(row=0, column=3, padx=15)
        
        ttk.Label(self.frame_passeio, text="E-mail:", background="#ffffff").grid(row=1, column=0, sticky="w", pady=10)
        self.campos['email_local'] = ttk.Entry(self.frame_passeio, width=28, font=fonte_input)
        self.campos['email_local'].grid(row=1, column=1, padx=15, pady=10)
        
        ttk.Label(self.frame_passeio, text="Telefone:", background="#ffffff").grid(row=1, column=2, sticky="w", padx=(20,0), pady=10)
        self.campos['telefone_local'] = ttk.Entry(self.frame_passeio, width=28, font=fonte_input)
        self.campos['telefone_local'].grid(row=1, column=3, sticky="w", padx=15, pady=10)
        
        self.campos['autorizacao_pais'] = tk.BooleanVar()
        ttk.Checkbutton(self.frame_passeio, text="Exige Autorização", variable=self.campos['autorizacao_pais']).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10,0))

        ttk.Label(form_frame, text="Conteúdo / Plano:", background="#ffffff").grid(row=4, column=0, sticky="nw", pady=15)
        self.obs_text = tk.Text(form_frame, height=8, width=80, font=self.fonte_padrao, relief="flat", borderwidth=1, highlightthickness=1, highlightbackground="#E2E8F0")
        self.obs_text.grid(row=4, column=1, columnspan=3, sticky="w", padx=15, pady=15)

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=20)
        ttk.Button(btn_frame, text="💾 Salvar Aula", style="Primary.TButton", command=self._salvar_aula).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="❌ Cancelar", command=self._cancelar_edicao).pack(side="left", padx=5)

    def _atualizar_dropdown_bncc(self, event=None):
        disc = self.campos['disciplina'].get().lower()
        if 'ingl' in disc: codigos = ["EF06LI01", "EF06LI04", "EF07LI01", "EF07LI12", "EF08LI05", "EF09LI02"]
        elif 'arte' in disc: codigos = ["EF69AR01 (Visuais)", "EF69AR04 (Visuais)", "EF69AR09 (Dança)", "EF69AR16 (Música)", "EF69AR24 (Teatro)"]
        else: codigos = []
        self.campos['bncc'].config(values=codigos)

    def _clonar_aula(self):
        sel = self.tree_aulas.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma aula na lista primeiro.")
            return
            
        aula_id = sel[0]
        aula_original = next((a for a in self.aulas_registradas if a.id == aula_id), None)
        if not aula_original: return
        
        self.aula_em_edicao = None
        self.campos['data'].set_date(date.today())
        self.campos['turma'].set(aula_original.turma)
        self.campos['disciplina'].set(aula_original.disciplina)
        self._atualizar_dropdown_bncc()
        self.campos['bncc'].set(aula_original.bncc)
        self.campos['categoria'].set(aula_original.categoria)
        
        self.campos['nome_local'].delete(0, tk.END); self.campos['nome_local'].insert(0, aula_original.nome_local)
        self.campos['endereco_local'].delete(0, tk.END); self.campos['endereco_local'].insert(0, aula_original.endereco_local)
        self.campos['email_local'].delete(0, tk.END); self.campos['email_local'].insert(0, aula_original.email_local)
        self.campos['telefone_local'].delete(0, tk.END); self.campos['telefone_local'].insert(0, aula_original.telefone_local)
        self.campos['autorizacao_pais'].set(aula_original.autorizacao_pais)
        
        self.obs_text.delete("1.0", tk.END); self.obs_text.insert("1.0", aula_original.observacoes)
        self._toggle_campos_passeio()
        self.notebook.select(self.aba_editor)
        messagebox.showinfo("🐑 Modo Clonagem", "Dados copiados! Modifique a data/turma e salve.")

    def _exportar_google_calendar(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".ics", filetypes=[("Arquivo iCalendar", "*.ics")])
        if not caminho: return
        try:
            self.servico.exportar_ics(self.aulas_registradas, caminho)
            messagebox.showinfo("Sucesso", "Arquivo .ics gerado!")
        except Exception as e: messagebox.showerror("Erro", str(e))

    def _salvar_aula(self):
        nova_aula = Aula(
            id=self.aula_em_edicao.id if self.aula_em_edicao else uuid.uuid4().hex,
            data=self.campos['data'].get_date().strftime("%Y-%m-%d"),
            turma=self.campos['turma'].get().strip(),
            disciplina=self.campos['disciplina'].get().strip(),
            categoria=self.campos['categoria'].get(),
            bncc=self.campos['bncc'].get().strip(),
            nome_local=self.campos['nome_local'].get().strip(),
            endereco_local=self.campos['endereco_local'].get().strip(),
            email_local=self.campos['email_local'].get().strip(),
            telefone_local=self.campos['telefone_local'].get().strip(),
            observacoes=self.obs_text.get("1.0", tk.END).strip(),
            autorizacao_pais=self.campos['autorizacao_pais'].get()
        )
        
        if not nova_aula.turma or not nova_aula.disciplina:
            messagebox.showerror("Erro", "Turma e Disciplina são obrigatórios.")
            return

        self.bd.salvar(nova_aula)
        self._recarregar_dados_banco()
        self._limpar_form()
        messagebox.showinfo("Sucesso", "Planejamento salvo!")
        self.notebook.select(self.aba_agenda)

    def _recarregar_dados_banco(self):
        self.aulas_registradas = self.bd.listar_todas()
        self._atualizar_lista()
        self._marcar_calendario()

    def _excluir_aula(self):
        sel = self.tree_aulas.selection()
        if not sel: return
        
        aula_id = sel[0]
        aula = next((a for a in self.aulas_registradas if a.id == aula_id), None)
        
        if aula and messagebox.askyesno("Confirmar", f"Excluir aula de {aula.disciplina}?"):
            self.bd.excluir(aula.id)
            self._recarregar_dados_banco()
            self._limpar_form()

    def _construir_aba_grade(self):
        container = ttk.Frame(self.aba_grade, padding=40)
        container.pack(fill="both", expand=True)
        card = ttk.Frame(container, style="Card.TFrame", padding=40)
        card.pack(fill="x")
        
        ttk.Label(card, text="⚡ Automação de Planejamento", font=("Inter", 18, "bold"), background="#ffffff", foreground="#2563EB").pack(anchor="w", pady=(0, 10))
        ttk.Label(card, text="Gere aulas automaticamente. O sistema respeita as Fronteiras do Ano Letivo.", font=self.fonte_padrao, background="#ffffff", foreground="#64748B").pack(anchor="w", pady=(0, 30))
        
        form = tk.Frame(card, background="#ffffff")
        form.pack(fill="x", pady=15)
        
        ttk.Label(form, text="Turma:", background="#ffffff").grid(row=0, column=0, sticky="w")
        self.combo_turma_grade = ttk.Combobox(form, values=self.turmas_cadastradas, width=30, font=self.fonte_padrao)
        self.combo_turma_grade.grid(row=1, column=0, padx=(0, 20), pady=10)
        
        ttk.Label(form, text="Disciplina:", background="#ffffff").grid(row=0, column=1, sticky="w")
        self.combo_disc_grade = ttk.Combobox(form, values=self.disciplinas_cadastradas, width=30, font=self.fonte_padrao)
        self.combo_disc_grade.grid(row=1, column=1, padx=(0, 20), pady=10)
        
        dias_frame = ttk.LabelFrame(card, text="Dias da Semana", padding=20)
        dias_frame.pack(fill="x", pady=30)
        
        self.vars_dias_grade = []
        for i, nome in enumerate(["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]):
            var = tk.BooleanVar()
            self.vars_dias_grade.append((i, var))
            ttk.Checkbutton(dias_frame, text=nome, variable=var).pack(side="left", padx=25)

        ttk.Button(card, text="🚀 Gerar Grade Automática", style="Primary.TButton", command=self._executar_gerador).pack(pady=20)

    def _executar_gerador(self):
        turma = self.combo_turma_grade.get().strip()
        disc = self.combo_disc_grade.get().strip()
        dias_selecionados = [i for i, var in self.vars_dias_grade if var.get()]
        
        if not turma or not disc or not dias_selecionados: 
            messagebox.showwarning("Aviso", "Preencha Turma, Disciplina e selecione ao menos um dia.")
            return
            
        aulas_geradas, mensagem = self.servico.gerar_grade_automatica(turma, disc, dias_selecionados, self.eventos_especiais)
        
        if aulas_geradas > 0:
            self._recarregar_dados_banco()
            
            # Modal inteligente de Avaliação
            resposta = messagebox.askyesno(
                "Sucesso", 
                f"{aulas_geradas} aulas gravadas no banco de dados!\n\nDeseja definir as datas das Avaliações para esta turma agora?"
            )
            if resposta:
                JanelaAvaliacoes(self, self.servico, turma, disc)
            else:
                self.notebook.select(self.aba_agenda)
        else:
             messagebox.showwarning("Operação não realizada", mensagem)

    def _construir_aba_config(self):
        container = ttk.Frame(self.aba_config, padding=25)
        container.pack(fill="both", expand=True)
        pane = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        pane.pack(fill="both", expand=True)
        
        frame_esq = ttk.LabelFrame(pane, text="Fronteiras e Eventos do Calendário", padding=25)
        pane.add(frame_esq, weight=3)
        ttk.Label(frame_esq, text="Defina os marcos do ano letivo (obrigatório para gerar grades) e os feriados.", font=self.fonte_padrao, background="#ffffff", foreground="#64748B").pack(anchor="w", pady=(0, 20))

        form_evento = tk.Frame(frame_esq, background="#ffffff")
        form_evento.pack(fill="x", pady=(0, 25))
        
        self.ev_data = DateEntry(form_evento, width=15, date_pattern="yyyy-mm-dd", font=self.fonte_padrao)
        self.ev_data.grid(row=0, column=0, padx=5)
        self.ev_nome = ttk.Entry(form_evento, width=25, font=self.fonte_padrao)
        self.ev_nome.grid(row=0, column=1, padx=5)
        
        self.ev_tipo = ttk.Combobox(form_evento, values=[t.value for t in TipoEvento], state="readonly", width=20, font=self.fonte_padrao)
        self.ev_tipo.set(TipoEvento.FERIADO.value)
        self.ev_tipo.grid(row=0, column=2, padx=5)
        
        ttk.Button(form_evento, text="Adicionar", style="Primary.TButton", command=self._adicionar_evento).grid(row=0, column=3, padx=15)
        
        self.tree_eventos = ttk.Treeview(frame_esq, columns=("Data", "Nome", "Tipo"), show="headings", height=12)
        self.tree_eventos.heading("Data", text="Data"); self.tree_eventos.column("Data", width=100, anchor="center")
        self.tree_eventos.heading("Nome", text="Descrição"); self.tree_eventos.column("Nome", width=250)
        self.tree_eventos.heading("Tipo", text="Classificação"); self.tree_eventos.column("Tipo", width=150)
        self.tree_eventos.pack(fill="both", expand=True)
        
        ttk.Button(frame_esq, text="🗑️ Remover Selecionado", style="Danger.TButton", command=self._remover_evento).pack(anchor="e", pady=15)
        
        frame_dir = ttk.Frame(pane, style="Card.TFrame", padding=25)
        pane.add(frame_dir, weight=1)
        ttk.Label(frame_dir, text="Turmas", font=self.fonte_titulo, background="#ffffff").pack(anchor="w")
        self.text_turmas = tk.Text(frame_dir, height=8, width=20, font=self.fonte_codigo, relief="solid", borderwidth=1, highlightthickness=0)
        self.text_turmas.pack(fill="both", expand=True, pady=(10, 20))
        
        ttk.Label(frame_dir, text="Disciplinas", font=self.fonte_titulo, background="#ffffff").pack(anchor="w")
        self.text_disciplinas = tk.Text(frame_dir, height=8, width=20, font=self.fonte_codigo, relief="solid", borderwidth=1, highlightthickness=0)
        self.text_disciplinas.pack(fill="both", expand=True, pady=(10, 25))
        
        ttk.Button(frame_dir, text="💾 Salvar Configurações", style="Success.TButton", command=self._salvar_configuracoes).pack(fill="x")
        self._preencher_configuracoes_ui()

    def _adicionar_evento(self):
        if not self.ev_nome.get(): return
        tipo = self.ev_tipo.get()
        if tipo in [TipoEvento.INICIO_ANO.value, TipoEvento.FIM_ANO.value]:
            self.eventos_especiais = [e for e in self.eventos_especiais if e["tipo"] != tipo]
        self.eventos_especiais = [e for e in self.eventos_especiais if e["data"] != self.ev_data.get_date().strftime("%Y-%m-%d")]
        self.eventos_especiais.append({"data": self.ev_data.get_date().strftime("%Y-%m-%d"), "nome": self.ev_nome.get(), "tipo": tipo})
        self._salvar_configuracoes(silencioso=True)
        self.ev_nome.delete(0, tk.END)

    def _remover_evento(self):
        sel = self.tree_eventos.selection()
        if not sel: return
        data = self.tree_eventos.item(sel[0])['values'][0]
        self.eventos_especiais = [e for e in self.eventos_especiais if e["data"] != data]
        self._salvar_configuracoes(silencioso=True)

    def _preencher_configuracoes_ui(self):
        for i in self.tree_eventos.get_children(): self.tree_eventos.delete(i)
        for ev in sorted(self.eventos_especiais, key=lambda x: x["data"]):
            self.tree_eventos.insert("", tk.END, values=(ev["data"], ev["nome"], ev["tipo"]))
        self.text_turmas.delete("1.0", tk.END); self.text_turmas.insert(tk.END, "\n".join(self.turmas_cadastradas))
        self.text_disciplinas.delete("1.0", tk.END); self.text_disciplinas.insert(tk.END, "\n".join(self.disciplinas_cadastradas))

    def _salvar_configuracoes(self, silencioso=False):
        self.turmas_cadastradas = [t.strip() for t in self.text_turmas.get("1.0", tk.END).splitlines() if t.strip()]
        self.disciplinas_cadastradas = [d.strip() for d in self.text_disciplinas.get("1.0", tk.END).splitlines() if d.strip()]
        with ARQUIVO_CONFIGURACAO.open("w", encoding="utf-8") as f:
            json.dump({"eventos": self.eventos_especiais, "turmas": self.turmas_cadastradas, "disciplinas": self.disciplinas_cadastradas}, f, ensure_ascii=False, indent=2)
        self._preencher_configuracoes_ui()
        self._marcar_calendario()
        self.campos['turma'].config(values=self.turmas_cadastradas)
        self.campos['disciplina'].config(values=self.disciplinas_cadastradas)
        if not silencioso: messagebox.showinfo("Sucesso", "Configurações atualizadas!")

    def _carregar_configuracoes(self):
        try:
            with ARQUIVO_CONFIGURACAO.open("r", encoding="utf-8") as f: return json.load(f)
        except FileNotFoundError:
            return {} 
        except Exception as e:
            logging.error(f"Erro ao carregar configurações: {e}")
            return {}

    def _marcar_calendario(self):
        self.cal.calevent_remove("all")
        self.cal.tag_config("feriado", background="#EF4444", foreground="white")
        self.cal.tag_config("sabado_letivo", background="#10B981", foreground="white")
        self.cal.tag_config("marco_ano", background="#F59E0B", foreground="white")
        self.cal.tag_config("aula_normal", background="#2563EB", foreground="white")
        self.cal.tag_config("passeio", background="#8B5CF6", foreground="white")
        self.cal.tag_config("avaliacao", background="#DC2626", foreground="white")
        
        for ev in self.eventos_especiais:
            try:
                data_obj = date.fromisoformat(ev["data"])
                if ev["tipo"] in [TipoEvento.INICIO_ANO.value, TipoEvento.FIM_ANO.value]: tag = "marco_ano"
                elif ev["tipo"] in [TipoEvento.FERIADO.value, TipoEvento.RECESSO.value]: tag = "feriado"
                else: tag = "sabado_letivo"
                self.cal.calevent_create(data_obj, ev["nome"], tags=tag)
            except ValueError as e:
                logging.warning(f"Aviso de data no evento do calendário ({ev['data']}): {e}")
                
        dias_aulas = {}
        for aula in self.aulas_registradas:
            if aula.data not in dias_aulas: dias_aulas[aula.data] = "aula_normal"
            if aula.categoria == CategoriaAula.PASSEIO_CULTURA.value: dias_aulas[aula.data] = "passeio"
            if aula.categoria == CategoriaAula.AVALIACAO.value: dias_aulas[aula.data] = "avaliacao"
                
        for data_str, tag in dias_aulas.items():
            if not any(e["data"] == data_str for e in self.eventos_especiais if e["tipo"] != TipoEvento.SABADO_LETIVO.value):
                try: self.cal.calevent_create(date.fromisoformat(data_str), "Aula", tags=tag)
                except ValueError as e: logging.warning(f"Aviso de data da aula no calendário ({data_str}): {e}")
        self._ao_selecionar_data_calendario(None)

    def _ao_selecionar_data_calendario(self, event):
        data_str = self.cal.get_date()
        try: 
            self.campos['data'].set_date(datetime.strptime(data_str, "%Y-%m-%d").date())
        except ValueError as e:
            logging.warning(f"Data selecionada inválida ({data_str}): {e}")
            return
        
        resumo = []
        for e in [ev for ev in self.eventos_especiais if ev["data"] == data_str]:
            icone = "⭐" if e["tipo"] in [TipoEvento.INICIO_ANO.value, TipoEvento.FIM_ANO.value] else ("🔴" if e["tipo"] != TipoEvento.SABADO_LETIVO.value else "🟢")
            resumo.append(f"{icone} {e['tipo']}: {e['nome']}")
                
        for a in [au for au in self.aulas_registradas if au.data == data_str]:
            icone = "📍" if a.categoria == CategoriaAula.PASSEIO_CULTURA.value else ("📝" if a.categoria == CategoriaAula.AVALIACAO.value else "📘")
            resumo.append(f"{icone} {a.turma} - {a.disciplina} ({a.categoria})")
            
        self.lbl_resumo_dia.config(text="\n\n".join(resumo) if resumo else "Nenhum evento agendado para este dia.", foreground="#1E293B" if resumo else "#94A3B8")

    def _atualizar_lista(self):
        for item in self.tree_aulas.get_children(): self.tree_aulas.delete(item)
        mes_atual = f"{date.today().year}-{date.today().month:02d}"
        
        for aula in self.aulas_registradas:
            if self.filtro_mes_atual.get() and not aula.data.startswith(mes_atual): continue
            try:
                d_br = datetime.strptime(aula.data, "%Y-%m-%d").strftime("%d/%m/%Y")
                self.tree_aulas.insert("", tk.END, iid=aula.id, values=(d_br, aula.turma, aula.disciplina, aula.categoria, aula.bncc), tags=(aula.categoria,))
            except ValueError as e:
                logging.warning(f"Erro ao formatar data da aula {aula.id} para listagem ({aula.data}): {e}")

    def _nova_aula_pelo_calendario(self):
        self._cancelar_edicao()
        self._ao_selecionar_data_calendario(None)
        self.notebook.select(self.aba_editor)

    def _editar_aula_selecionada(self):
        sel = self.tree_aulas.selection()
        if not sel: return
        
        aula_id = sel[0]
        self.aula_em_edicao = next((a for a in self.aulas_registradas if a.id == aula_id), None)
        
        if not self.aula_em_edicao: return
        
        self.campos['data'].set_date(datetime.strptime(self.aula_em_edicao.data, "%Y-%m-%d").date())
        self.campos['turma'].set(self.aula_em_edicao.turma)
        self.campos['disciplina'].set(self.aula_em_edicao.disciplina)
        self._atualizar_dropdown_bncc()
        self.campos['bncc'].set(self.aula_em_edicao.bncc)
        self.campos['categoria'].set(self.aula_em_edicao.categoria)
        
        self.campos['nome_local'].delete(0, tk.END); self.campos['nome_local'].insert(0, self.aula_em_edicao.nome_local)
        self.campos['endereco_local'].delete(0, tk.END); self.campos['endereco_local'].insert(0, self.aula_em_edicao.endereco_local)
        self.campos['email_local'].delete(0, tk.END); self.campos['email_local'].insert(0, self.aula_em_edicao.email_local)
        self.campos['telefone_local'].delete(0, tk.END); self.campos['telefone_local'].insert(0, self.aula_em_edicao.telefone_local)
        self.campos['autorizacao_pais'].set(self.aula_em_edicao.autorizacao_pais)
        
        self.obs_text.delete("1.0", tk.END); self.obs_text.insert("1.0", self.aula_em_edicao.observacoes)
        self._toggle_campos_passeio()
        self.notebook.select(self.aba_editor)

    def _cancelar_edicao(self):
        self._limpar_form()
        self.notebook.select(self.aba_agenda)

    def _limpar_form(self):
        self.aula_em_edicao = None
        self.campos['data'].set_date(date.today())
        self.campos['turma'].set(''); self.campos['disciplina'].set(''); self.campos['bncc'].set('')
        self.campos['categoria'].set(CategoriaAula.TEORICA.value)
        
        self.campos['nome_local'].delete(0, tk.END); self.campos['endereco_local'].delete(0, tk.END)
        self.campos['email_local'].delete(0, tk.END); self.campos['telefone_local'].delete(0, tk.END)
        self.campos['autorizacao_pais'].set(False)
        
        self.obs_text.delete("1.0", tk.END)
        self._toggle_campos_passeio()

    def _toggle_campos_passeio(self, event=None):
        if self.campos['categoria'].get() == CategoriaAula.PASSEIO_CULTURA.value: self.frame_passeio.grid()
        else: self.frame_passeio.grid_remove()

    def _exportar_pdf(self):
        sel = self.tree_aulas.selection()
        if not sel: return
        
        aula_id = sel[0]
        aula = next((a for a in self.aulas_registradas if a.id == aula_id), None)
        if not aula: return
        
        caminho = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf"), ("TXT", "*.txt")])
        if not caminho: return
        self.servico.exportar_pdf(aula, caminho)
        messagebox.showinfo("Exportado", "Relatório exportado!")

if __name__ == "__main__":
    app = PlanejadorApp()
    app.mainloop()
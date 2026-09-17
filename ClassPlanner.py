import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkcalendar import Calendar, DateEntry
except ImportError as exc:
    raise SystemExit("Instale a biblioteca 'tkcalendar' antes de executar: pip3 install tkcalendar") from exc

ARQUIVO_CONFIGURACAO = Path(__file__).with_name("configuracoes_calendario.json")
ARQUIVO_AGENDA_JSON_ANTIGO = Path(__file__).with_name("agenda_aulas.json")
BANCO_DADOS_AULAS = Path(__file__).with_name("banco_aulas.db")

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

# ================= ARQUITETURA MVC: CAMADA MODEL (BANCO DE DADOS) =================
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

    def listar_todas(self) -> list[Aula]:
        cursor = self.conn.execute('SELECT * FROM aulas ORDER BY data ASC')
        return [self._linha_para_aula(row) for row in cursor.fetchall()]

    def salvar(self, aula: Aula):
        with self.conn:
            self.conn.execute('''
                INSERT INTO aulas (id, data, turma, disciplina, categoria, bncc, nome_local, endereco_local, observacoes, autorizacao_pais)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data=excluded.data, turma=excluded.turma, disciplina=excluded.disciplina,
                    categoria=excluded.categoria, bncc=excluded.bncc, nome_local=excluded.nome_local,
                    endereco_local=excluded.endereco_local, observacoes=excluded.observacoes,
                    autorizacao_pais=excluded.autorizacao_pais
            ''', (aula.id, aula.data, aula.turma, aula.disciplina, aula.categoria, aula.bncc, 
                  aula.nome_local, aula.endereco_local, aula.observacoes, int(aula.autorizacao_pais)))

    def excluir(self, aula_id: str):
        with self.conn:
            self.conn.execute('DELETE FROM aulas WHERE id = ?', (aula_id,))

    def _linha_para_aula(self, row) -> Aula:
        return Aula(
            id=row['id'], data=row['data'], turma=row['turma'], disciplina=row['disciplina'],
            categoria=row['categoria'], bncc=row['bncc'], nome_local=row['nome_local'],
            endereco_local=row['endereco_local'], observacoes=row['observacoes'],
            autorizacao_pais=bool(row['autorizacao_pais'])
        )

# ================= ARQUITETURA MVC: CAMADA VIEW / CONTROLLER =================
class PlanejadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Planejador de Aulas - Dashboard do Professor")
        self.geometry("1280x780")
        self.minsize(1100, 680)
        
        self._aplicar_tema_moderno()
        
        # Conexão com o SQLite
        self.bd = RepositorioAulas(BANCO_DADOS_AULAS)
        self._migrar_json_antigo() # Garante que nada se perca da versão anterior
        
        self.aulas_registradas = self.bd.listar_todas()
        
        # Configurações em JSON (Bom para metadados simples)
        self.config_dados = self._carregar_configuracoes()
        self.eventos_especiais = self.config_dados.get("eventos", [])
        self.turmas_cadastradas = self.config_dados.get("turmas", ["6º Ano A", "7º Ano A", "8º Ano A", "9º Ano A"])
        self.disciplinas_cadastradas = self.config_dados.get("disciplinas", ["Inglês", "Artes"])
        
        self.aula_em_edicao = None
        
        self._criar_interface()
        self._marcar_calendario()

    def _aplicar_tema_moderno(self):
        self.configure(bg="#f4f6f9")
        style = ttk.Style(self)
        style.theme_use('clam')
        
        style.configure(".", background="#f4f6f9", foreground="#333333", font=("Segoe UI", 10))
        style.configure("TNotebook", background="#f4f6f9", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[20, 10], font=("Segoe UI", 10, "bold"), background="#e0e0e0")
        style.map("TNotebook.Tab", background=[("selected", "#005b9f")], foreground=[("selected", "white")])
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabelframe", background="#ffffff", font=("Segoe UI", 11, "bold"))
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#005b9f")
        
        style.configure("Primary.TButton", background="#005b9f", foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("Success.TButton", background="#28a745", foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("Warning.TButton", background="#ffc107", foreground="black", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background="#dc3545", foreground="white", font=("Segoe UI", 10, "bold"))

    def _migrar_json_antigo(self):
        # Lógica para não perder as aulas que você salvou ontem!
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
                        observacoes=item.get("observacoes", ""),
                        autorizacao_pais=item.get("autorizacao_pais", False)
                    )
                    self.bd.salvar(aula)
                # Renomeia para backup após migrar com sucesso
                os.rename(ARQUIVO_AGENDA_JSON_ANTIGO, str(ARQUIVO_AGENDA_JSON_ANTIGO) + ".bkp")
                messagebox.showinfo("Migração Concluída", "Seus dados foram migrados com segurança para o novo Banco de Dados (SQLite)!")
            except Exception as e:
                print(f"Falha na migração: {e}")

    def _criar_interface(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=15)
        
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

    # ================= ABA 1: AGENDA GERAL =================
    def _construir_aba_agenda(self):
        pane = ttk.PanedWindow(self.aba_agenda, orient=tk.HORIZONTAL)
        pane.pack(fill="both", expand=True, pady=10)
        
        frame_cal = ttk.Frame(pane, style="Card.TFrame", padding=15)
        pane.add(frame_cal, weight=1)
        ttk.Label(frame_cal, text="Selecione uma data:", font=("Segoe UI", 12, "bold"), background="#ffffff").pack(anchor="w", pady=(0,10))
        
        self.cal = Calendar(frame_cal, selectmode="day", date_pattern="yyyy-mm-dd", font=("Segoe UI", 10), 
                            background="white", foreground="black", bordercolor="#e0e0e0",
                            headersbackground="#005b9f", headersforeground="white", 
                            selectbackground="#005b9f", selectforeground="white")
        self.cal.pack(fill="both", expand=True)
        self.cal.bind("<<CalendarSelected>>", self._ao_selecionar_data_calendario)
        
        self.frame_resumo = ttk.LabelFrame(frame_cal, text="Resumo do Dia Selecionado", padding=10)
        self.frame_resumo.pack(fill="x", pady=15)
        self.lbl_resumo_dia = ttk.Label(self.frame_resumo, text="...", font=("Segoe UI", 10), background="#ffffff", wraplength=300)
        self.lbl_resumo_dia.pack(anchor="w")

        frame_lista = ttk.Frame(pane, style="Card.TFrame", padding=15)
        pane.add(frame_lista, weight=2)
        ttk.Label(frame_lista, text="Aulas Registradas no Banco", font=("Segoe UI", 12, "bold"), background="#ffffff").pack(anchor="w", pady=(0,10))
        
        self.lista_aulas = tk.Listbox(frame_lista, font=("Consolas", 11), selectbackground="#005b9f", relief="flat")
        self.lista_aulas.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=self.lista_aulas.yview)
        scroll.pack(side="right", fill="y")
        self.lista_aulas.config(yscrollcommand=scroll.set)
        
        frame_botoes = ttk.Frame(self.aba_agenda)
        frame_botoes.pack(fill="x", pady=10)
        
        ttk.Button(frame_botoes, text="➕ Nova", style="Primary.TButton", command=self._nova_aula_pelo_calendario).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="✏️ Editar", command=self._editar_aula_selecionada).pack(side="left", padx=5)
        
        # BOTÃO NOVO: CLONAR
        ttk.Button(frame_botoes, text="🐑 Clonar", style="Warning.TButton", command=self._clonar_aula).pack(side="left", padx=5)
        ttk.Button(frame_botoes, text="🗑️ Excluir", style="Danger.TButton", command=self._excluir_aula).pack(side="left", padx=5)
        
        # BOTÃO NOVO: GOOGLE CALENDAR
        ttk.Button(frame_botoes, text="☁️ Google Calendar (.ics)", style="Success.TButton", command=self._exportar_google_calendar).pack(side="right", padx=5)
        ttk.Button(frame_botoes, text="📄 PDF", command=self._exportar_pdf).pack(side="right", padx=5)
        
        self._atualizar_lista()

    # ================= ABA 2: EDITOR DE AULA (COM BNCC) =================
    def _construir_aba_editor(self):
        form_frame = ttk.LabelFrame(self.aba_editor, text="Detalhes do Planejamento", padding=25)
        form_frame.pack(fill="both", expand=True, padx=40, pady=20)
        
        self.campos = {}
        
        ttk.Label(form_frame, text="Data:", background="#ffffff").grid(row=0, column=0, sticky="w", pady=10)
        self.campos['data'] = DateEntry(form_frame, width=15, background='#005b9f', foreground='white', borderwidth=0, date_pattern="yyyy-mm-dd", font=("Segoe UI", 10))
        self.campos['data'].grid(row=0, column=1, sticky="w", padx=10)
        
        ttk.Label(form_frame, text="Turma:", background="#ffffff").grid(row=1, column=0, sticky="w", pady=10)
        self.campos['turma'] = ttk.Combobox(form_frame, values=self.turmas_cadastradas, width=25, font=("Segoe UI", 10))
        self.campos['turma'].grid(row=1, column=1, sticky="w", padx=10)

        ttk.Label(form_frame, text="Disciplina:", background="#ffffff").grid(row=1, column=2, sticky="w", pady=10, padx=(30,0))
        self.campos['disciplina'] = ttk.Combobox(form_frame, values=self.disciplinas_cadastradas, width=25, font=("Segoe UI", 10))
        self.campos['disciplina'].grid(row=1, column=3, sticky="w", padx=10)
        self.campos['disciplina'].bind("<<ComboboxSelected>>", self._atualizar_dropdown_bncc)

        ttk.Label(form_frame, text="Categoria:", background="#ffffff").grid(row=2, column=0, sticky="w", pady=10)
        self.campos['categoria'] = ttk.Combobox(form_frame, values=[c.value for c in CategoriaAula], state="readonly", width=25, font=("Segoe UI", 10))
        self.campos['categoria'].set(CategoriaAula.TEORICA.value)
        self.campos['categoria'].grid(row=2, column=1, sticky="w", padx=10)
        self.campos['categoria'].bind("<<ComboboxSelected>>", self._toggle_campos_passeio)

        ttk.Label(form_frame, text="Cód. BNCC:", background="#ffffff").grid(row=2, column=2, sticky="w", pady=10, padx=(30,0))
        self.campos['bncc'] = ttk.Combobox(form_frame, values=[], width=25, font=("Segoe UI", 10))
        self.campos['bncc'].grid(row=2, column=3, sticky="w", padx=10)

        self.frame_passeio = ttk.Frame(form_frame, style="Card.TFrame")
        self.frame_passeio.grid(row=3, column=0, columnspan=4, sticky="ew", pady=10)
        self.frame_passeio.grid_remove()

        ttk.Label(self.frame_passeio, text="Local:", background="#ffffff").grid(row=0, column=0, sticky="w")
        self.campos['nome_local'] = ttk.Entry(self.frame_passeio, width=25, font=("Segoe UI", 10))
        self.campos['nome_local'].grid(row=0, column=1, padx=10)
        
        ttk.Label(self.frame_passeio, text="Endereço:", background="#ffffff").grid(row=0, column=2, sticky="w", padx=(20,0))
        self.campos['endereco_local'] = ttk.Entry(self.frame_passeio, width=35, font=("Segoe UI", 10))
        self.campos['endereco_local'].grid(row=0, column=3, padx=10)
        
        self.campos['autorizacao_pais'] = tk.BooleanVar()
        ttk.Checkbutton(self.frame_passeio, text="Exige Autorização", variable=self.campos['autorizacao_pais']).grid(row=1, column=0, columnspan=4, sticky="w", pady=15)

        ttk.Label(form_frame, text="Conteúdo:", background="#ffffff").grid(row=4, column=0, sticky="nw", pady=10)
        self.obs_text = tk.Text(form_frame, height=8, width=70, font=("Segoe UI", 10), relief="solid", borderwidth=1)
        self.obs_text.grid(row=4, column=1, columnspan=3, sticky="w", padx=10)

        btn_frame = ttk.Frame(self.aba_editor)
        btn_frame.pack(fill="x", padx=40, pady=10)
        ttk.Button(btn_frame, text="💾 Salvar (SQL)", style="Primary.TButton", command=self._salvar_aula).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="❌ Voltar", command=self._cancelar_edicao).pack(side="left", padx=5)

    def _atualizar_dropdown_bncc(self, event=None):
        # Mapeamento dinâmico baseado na disciplina
        disc = self.campos['disciplina'].get().lower()
        if 'ingl' in disc:
            codigos = ["EF06LI01", "EF06LI04", "EF07LI01", "EF07LI12", "EF08LI05", "EF09LI02"]
        elif 'arte' in disc:
            codigos = ["EF69AR01 (Visuais)", "EF69AR04 (Visuais)", "EF69AR09 (Dança)", "EF69AR16 (Música)", "EF69AR24 (Teatro)"]
        else:
            codigos = []
        self.campos['bncc'].config(values=codigos)

    # ================= FUNCIONALIDADES PRINCIPAIS (CRUD E LÓGICA) =================
    def _clonar_aula(self):
        if not self.lista_aulas.curselection():
            messagebox.showwarning("Aviso", "Selecione uma aula na lista primeiro.")
            return
            
        idx = self.lista_aulas.curselection()[0]
        aula_original = self.aulas_registradas[idx]
        
        # Seta como Nova Aula
        self.aula_em_edicao = None
        
        self.campos['data'].set_date(date.today())
        self.campos['turma'].set(aula_original.turma)
        self.campos['disciplina'].set(aula_original.disciplina)
        self._atualizar_dropdown_bncc() # Dispara preenchimento
        self.campos['bncc'].set(aula_original.bncc)
        self.campos['categoria'].set(aula_original.categoria)
        
        self.campos['nome_local'].delete(0, tk.END)
        self.campos['nome_local'].insert(0, aula_original.nome_local)
        self.campos['endereco_local'].delete(0, tk.END)
        self.campos['endereco_local'].insert(0, aula_original.endereco_local)
        self.campos['autorizacao_pais'].set(aula_original.autorizacao_pais)
        
        self.obs_text.delete("1.0", tk.END)
        self.obs_text.insert("1.0", aula_original.observacoes)
        
        self._toggle_campos_passeio()
        self.notebook.select(self.aba_editor)
        messagebox.showinfo("🐑 Modo Clonagem", "Os dados foram copiados. Modifique a nova data ou turma e clique em Salvar!")

    def _exportar_google_calendar(self):
        # Gera o arquivo padrão iCalendar (ICS) offline, eliminando complexidade do OAuth2.
        if not self.aulas_registradas:
            messagebox.showinfo("Aviso", "Não há aulas no banco de dados para exportar.")
            return
            
        caminho = filedialog.asksaveasfilename(
            defaultextension=".ics",
            filetypes=[("Arquivo iCalendar", "*.ics")],
            title="Exportar para Nuvem"
        )
        if not caminho: return

        linhas = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Planejador de Aulas by Leonardo O.//BR",
            "CALSCALE:GREGORIAN"
        ]
        
        for aula in self.aulas_registradas:
            try:
                data_obj = datetime.strptime(aula.data, "%Y-%m-%d")
                dt_str = data_obj.strftime("%Y%m%d")
                # Define aula padrão das 08h00 as 09h00, no GCal o usuário arrasta
                linhas.append("BEGIN:VEVENT")
                linhas.append(f"UID:{aula.id}@planejador.com")
                linhas.append(f"DTSTART;TZID=America/Sao_Paulo:{dt_str}T080000")
                linhas.append(f"DTEND;TZID=America/Sao_Paulo:{dt_str}T090000")
                
                titulo = f"{aula.disciplina} ({aula.turma}) - {aula.categoria}"
                linhas.append(f"SUMMARY:{titulo}")
                
                desc = f"BNCC: {aula.bncc}\\n\\n" + aula.observacoes.replace("\n", "\\n")
                linhas.append(f"DESCRIPTION:{desc}")
                
                if aula.categoria == CategoriaAula.PASSEIO_CULTURA.value:
                    linhas.append(f"LOCATION:{aula.endereco_local} - {aula.nome_local}")
                    
                linhas.append("END:VEVENT")
            except Exception as e:
                print(f"Erro ao processar aula pro iCS: {e}")
                
        linhas.append("END:VCALENDAR")
        
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))
            
        messagebox.showinfo("Sucesso", "Arquivo .ics gerado!\nAbra este arquivo no celular ou importe no Google Calendar Web para preencher sua agenda instantaneamente!")

    def _salvar_aula(self):
        nova_aula = Aula(
            id=self.aula_em_edicao.id if self.aula_em_edicao else uuid.uuid4().hex, # Gera UUID se novo
            data=self.campos['data'].get(),
            turma=self.campos['turma'].get().strip(),
            disciplina=self.campos['disciplina'].get().strip(),
            categoria=self.campos['categoria'].get(),
            bncc=self.campos['bncc'].get().strip(),
            nome_local=self.campos.get('nome_local').get(),
            endereco_local=self.campos.get('endereco_local').get(),
            observacoes=self.obs_text.get("1.0", tk.END).strip(),
            autorizacao_pais=self.campos['autorizacao_pais'].get()
        )
        
        if not nova_aula.turma or not nova_aula.disciplina:
            messagebox.showerror("Erro", "Turma e Disciplina são obrigatórios.")
            return

        self.bd.salvar(nova_aula) # Salva no SQLite
        
        self._recarregar_dados_banco()
        self._limpar_form()
        messagebox.showinfo("Sucesso", "Planejamento salvo no Banco de Dados!")
        self.notebook.select(self.aba_agenda)

    def _recarregar_dados_banco(self):
        self.aulas_registradas = self.bd.listar_todas()
        self._atualizar_lista()
        self._marcar_calendario()

    def _excluir_aula(self):
        if not self.lista_aulas.curselection(): return
        idx = self.lista_aulas.curselection()[0]
        aula = self.aulas_registradas[idx]
        
        if messagebox.askyesno("Confirmar", f"Excluir aula de {aula.disciplina}?"):
            self.bd.excluir(aula.id) # Remove do SQLite
            self._recarregar_dados_banco()
            self._limpar_form()

    # (Métodos auxiliares mantidos e adaptados para o BD)
    def _construir_aba_grade(self):
        container = ttk.Frame(self.aba_grade, style="Card.TFrame", padding=30)
        container.pack(fill="both", expand=True, padx=40, pady=20)
        
        ttk.Label(container, text="⚡ Automação de Planejamento", font=("Segoe UI", 16, "bold"), background="#ffffff", foreground="#005b9f").pack(anchor="w", pady=(0, 5))
        
        form = ttk.Frame(container, style="Card.TFrame")
        form.pack(fill="x", pady=15)
        self.combo_turma_grade = ttk.Combobox(form, values=self.turmas_cadastradas, width=25, font=("Segoe UI", 10))
        self.combo_turma_grade.grid(row=0, column=0, padx=10)
        self.combo_disc_grade = ttk.Combobox(form, values=self.disciplinas_cadastradas, width=25, font=("Segoe UI", 10))
        self.combo_disc_grade.grid(row=0, column=1, padx=10)
        
        dias_frame = ttk.LabelFrame(container, text="Dias da Semana", padding=15)
        dias_frame.pack(fill="x", pady=25)
        
        self.vars_dias_grade = []
        for i, nome in enumerate(["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]):
            var = tk.BooleanVar()
            self.vars_dias_grade.append((i, var))
            ttk.Checkbutton(dias_frame, text=nome, variable=var).pack(side="left", padx=20)

        ttk.Button(container, text="🚀 Gerar Grade no Banco", style="Primary.TButton", command=self._executar_gerador).pack(pady=20)

    def _executar_gerador(self):
        turma = self.combo_turma_grade.get().strip()
        disc = self.combo_disc_grade.get().strip()
        dias_selecionados = [i for i, var in self.vars_dias_grade if var.get()]
        
        if not turma or not disc or not dias_selecionados: return
            
        aulas_geradas = 0
        dias_bloqueados = [e["data"] for e in self.eventos_especiais if e["tipo"] in [TipoEvento.FERIADO.value, TipoEvento.RECESSO.value]]
        
        for i in range(60):
            data_alvo = date.today() + timedelta(days=i)
            data_str = data_alvo.strftime("%Y-%m-%d")
            
            if data_alvo.weekday() in dias_selecionados and data_str not in dias_bloqueados:
                existe = any(a.data == data_str and a.turma == turma and a.disciplina == disc for a in self.aulas_registradas)
                if not existe:
                    nova_aula = Aula(
                        id=uuid.uuid4().hex, data=data_str, turma=turma, disciplina=disc,
                        categoria=CategoriaAula.TEORICA.value, bncc="", observacoes="Gerada automaticamente."
                    )
                    self.bd.salvar(nova_aula) # Grava direto no SQLite
                    aulas_geradas += 1
        
        if aulas_geradas > 0:
            self._recarregar_dados_banco()
            messagebox.showinfo("Sucesso", f"{aulas_geradas} aulas gravadas no banco de dados!")
            self.notebook.select(self.aba_agenda)

    def _construir_aba_config(self):
        pane = ttk.PanedWindow(self.aba_config, orient=tk.HORIZONTAL)
        pane.pack(fill="both", expand=True, padx=10, pady=10)
        
        frame_esq = ttk.LabelFrame(pane, text="Gestão de Datas Especiais", padding=15)
        pane.add(frame_esq, weight=3)
        
        form_evento = ttk.Frame(frame_esq, style="Card.TFrame")
        form_evento.pack(fill="x", pady=(0, 15))
        self.ev_data = DateEntry(form_evento, width=12, date_pattern="yyyy-mm-dd", font=("Segoe UI", 10))
        self.ev_data.grid(row=0, column=0, padx=5)
        self.ev_nome = ttk.Entry(form_evento, width=20, font=("Segoe UI", 10))
        self.ev_nome.grid(row=0, column=1, padx=5)
        self.ev_tipo = ttk.Combobox(form_evento, values=[t.value for t in TipoEvento], state="readonly", width=12, font=("Segoe UI", 10))
        self.ev_tipo.set(TipoEvento.FERIADO.value)
        self.ev_tipo.grid(row=0, column=2, padx=5)
        ttk.Button(form_evento, text="Adicionar", style="Primary.TButton", command=self._adicionar_evento).grid(row=0, column=3, padx=10)
        
        self.tree_eventos = ttk.Treeview(frame_esq, columns=("Data", "Nome", "Tipo"), show="headings", height=10)
        for col in ("Data", "Nome", "Tipo"): self.tree_eventos.heading(col, text=col)
        self.tree_eventos.pack(fill="both", expand=True)
        ttk.Button(frame_esq, text="🗑️ Remover", style="Danger.TButton", command=self._remover_evento).pack(anchor="e", pady=10)
        
        frame_dir = ttk.Frame(pane)
        pane.add(frame_dir, weight=1)
        self.text_turmas = tk.Text(frame_dir, height=8, width=20, font=("Consolas", 10))
        self.text_turmas.pack(fill="both", expand=True, pady=5)
        self.text_disciplinas = tk.Text(frame_dir, height=8, width=20, font=("Consolas", 10))
        self.text_disciplinas.pack(fill="both", expand=True, pady=5)
        ttk.Button(frame_dir, text="💾 Salvar Configurações", style="Primary.TButton", command=self._salvar_configuracoes).pack(fill="x")
        self._preencher_configuracoes_ui()

    def _adicionar_evento(self):
        if not self.ev_nome.get(): return
        self.eventos_especiais = [e for e in self.eventos_especiais if e["data"] != self.ev_data.get()]
        self.eventos_especiais.append({"data": self.ev_data.get(), "nome": self.ev_nome.get(), "tipo": self.ev_tipo.get()})
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
        except: return {}

    def _marcar_calendario(self):
        self.cal.calevent_remove("all")
        self.cal.tag_config("feriado", background="#dc3545", foreground="white")
        self.cal.tag_config("sabado_letivo", background="#28a745", foreground="white")
        self.cal.tag_config("aula_normal", background="#005b9f", foreground="white")
        self.cal.tag_config("passeio", background="#fd7e14", foreground="white")
        
        for ev in self.eventos_especiais:
            try:
                data_obj = date.fromisoformat(ev["data"])
                tag = "feriado" if ev["tipo"] in [TipoEvento.FERIADO.value, TipoEvento.RECESSO.value] else "sabado_letivo"
                self.cal.calevent_create(data_obj, ev["nome"], tags=tag)
            except: pass
                
        dias_aulas = {}
        for aula in self.aulas_registradas:
            if aula.data not in dias_aulas: dias_aulas[aula.data] = "aula_normal"
            if aula.categoria == CategoriaAula.PASSEIO_CULTURA.value: dias_aulas[aula.data] = "passeio"
                
        for data_str, tag in dias_aulas.items():
            if not any(e["data"] == data_str for e in self.eventos_especiais if e["tipo"] != TipoEvento.SABADO_LETIVO.value):
                try: self.cal.calevent_create(date.fromisoformat(data_str), "Aula", tags=tag)
                except: pass
        self._ao_selecionar_data_calendario(None)

    def _ao_selecionar_data_calendario(self, event):
        data_str = self.cal.get_date()
        try: self.campos['data'].set_date(datetime.strptime(data_str, "%Y-%m-%d").date())
        except: return
        
        resumo = []
        for e in [ev for ev in self.eventos_especiais if ev["data"] == data_str]:
            icone = "🔴" if e["tipo"] != TipoEvento.SABADO_LETIVO.value else "🟢"
            resumo.append(f"{icone} {e['tipo']}: {e['nome']}")
                
        for a in [au for au in self.aulas_registradas if au.data == data_str]:
            icone = "🟠" if a.categoria == CategoriaAula.PASSEIO_CULTURA.value else "🔵"
            resumo.append(f"{icone} {a.turma} - {a.disciplina} ({a.bncc})")
            
        self.lbl_resumo_dia.config(text="\n".join(resumo) if resumo else "Nenhum evento para este dia.", foreground="black" if resumo else "#555")

    def _atualizar_lista(self):
        self.lista_aulas.delete(0, tk.END)
        for aula in self.aulas_registradas:
            try:
                d_br = datetime.strptime(aula.data, "%Y-%m-%d").strftime("%d/%m/%Y")
                self.lista_aulas.insert(tk.END, f"[{d_br}] {aula.turma} | {aula.disciplina} | {aula.bncc}")
            except: pass

    def _nova_aula_pelo_calendario(self):
        self._cancelar_edicao()
        self._ao_selecionar_data_calendario(None)
        self.notebook.select(self.aba_editor)

    def _editar_aula_selecionada(self):
        if not self.lista_aulas.curselection(): return
        self.aula_em_edicao = self.aulas_registradas[self.lista_aulas.curselection()[0]]
        self.campos['data'].set_date(datetime.strptime(self.aula_em_edicao.data, "%Y-%m-%d").date())
        self.campos['turma'].set(self.aula_em_edicao.turma)
        self.campos['disciplina'].set(self.aula_em_edicao.disciplina)
        self._atualizar_dropdown_bncc()
        self.campos['bncc'].set(self.aula_em_edicao.bncc)
        self.campos['categoria'].set(self.aula_em_edicao.categoria)
        self.campos['nome_local'].delete(0, tk.END); self.campos['nome_local'].insert(0, self.aula_em_edicao.nome_local)
        self.campos['endereco_local'].delete(0, tk.END); self.campos['endereco_local'].insert(0, self.aula_em_edicao.endereco_local)
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
        self.campos['autorizacao_pais'].set(False)
        self.obs_text.delete("1.0", tk.END)
        self._toggle_campos_passeio()

    def _toggle_campos_passeio(self, event=None):
        if self.campos['categoria'].get() == CategoriaAula.PASSEIO_CULTURA.value: self.frame_passeio.grid()
        else: self.frame_passeio.grid_remove()

    def _exportar_pdf(self):
        if not self.lista_aulas.curselection(): return
        aula = self.aulas_registradas[self.lista_aulas.curselection()[0]]
        caminho = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf"), ("TXT", "*.txt")])
        if not caminho: return
        texto = f"Plano de Aula: {aula.data}\nTurma: {aula.turma} | Disciplina: {aula.disciplina}\nBNCC: {aula.bncc}\n\nObs:\n{aula.observacoes}"
        try:
            from reportlab.pdfgen import canvas
            pdf = canvas.Canvas(caminho)
            pdf.drawString(50, 800, f"Plano de Aula: {aula.data}")
            y = 770
            for linha in texto.splitlines():
                pdf.drawString(50, y, linha[:100]); y -= 20
            pdf.save()
            messagebox.showinfo("PDF Gerado", "Relatório exportado!")
        except:
            with open(caminho.replace('.pdf','.txt'), "w") as f: f.write(texto)

if __name__ == "__main__":
    app = PlanejadorApp()
    app.mainloop()

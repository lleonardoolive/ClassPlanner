import logging
import textwrap
import uuid
from datetime import datetime, timedelta
from models import Aula, CategoriaAula, TipoEvento
from database import RepositorioAulas

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
            return 0, "Marcos do ano letivo não definidos. Adicione 'Início do Ano Letivo' e 'Fim do Ano Letivo'."

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
            
            for linha_original in texto.splitlines():
                linhas_quebradas = textwrap.wrap(linha_original, width=80) 
                if not linhas_quebradas:
                    y -= 20
                for linha in linhas_quebradas:
                    pdf.drawString(50, y, linha)
                    y -= 20
                    if y < 50:
                        pdf.showPage()
                        y = 800
            pdf.save()
        except ImportError:
            logging.warning("Biblioteca ReportLab não encontrada. Salvando como txt.")
            with open(caminho.replace('.pdf','.txt'), "w", encoding="utf-8") as f: 
                f.write(texto)
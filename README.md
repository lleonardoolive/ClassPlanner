# ClassPlanner

Um organizador de aulas, horários e currículo escolar local feito em Python. Pensado para a realidade do professor brasileiro.

**Status atual:** Beta v0.8  
**Linguagem:** PT-BR  
**Licença:** MIT

---

## O projeto
Como professor, lidar com o planejamento de dezenas de turmas, diários e os códigos da BNCC é um trabalho extremamente repetitivo. O ClassPlanner nasceu para automatizar essa rotina. Ele é um aplicativo desktop leve, rápido e totalmente offline — sem depender de internet de escola ou mensalidades de plataformas educacionais.

A premissa é simples: você cadastra os limites do seu ano letivo, as suas turmas e feriados, e o sistema gera a estrutura do diário. Depois, é só preencher os conteúdos.

## A reestruturação (v0.8)
O projeto passou recentemente por uma grande refatoração. 
* **O Legado:** A primeira versão (`_ClassPlanner_Antigo.py`) era monolítica. Toda a interface e a lógica de persistência estavam juntas, salvando os dados de forma crua em um arquivo `agenda_aulas.json`.
* **O Atual:** O software agora possui uma arquitetura dividida em módulos (`ui.py`, `services.py`, `models.py`, `database.py`). Migramos a persistência das aulas para um banco de dados **SQLite**, garantindo mais segurança e velocidade na busca dos dados, além de preparar o terreno para relacionamentos mais complexos entre turmas, disciplinas e horários.

## O que já está funcionando
- **Gerador de Grade:** Automação que cria as aulas do ano inteiro baseado nos dias da semana e feriados cadastrados.
- **Editor de Planejamento:** Interface para definir o plano da aula, amarrando a categoria (Teórica, Prática, Avaliação, etc.) e o local.
- **Integração BNCC:** Inserção rápida dos códigos da Base Nacional Comum Curricular diretamente no plano da aula.
- **Exportação Básica:** Geração de PDF do plano diário e atalho para exportar a aula para o Google Calendar ou Outlook.

## Roadmap (Próximos Passos)
O projeto está em uso contínuo e temos um diagnóstico claro do que precisa ser implementado para chegar à versão 1.0 com funcionalidade plena:

**Prioridade Alta (Correções e Regras de Negócio):**
- [ ] **Aulas Geminadas:** Mudar a chave primária das validações para permitir registrar duas ou mais aulas da mesma disciplina no mesmo dia (ex: 1º e 2º horários).
- [ ] **Exportação ICS em Lote:** Restaurar a função de gerar um único arquivo `.ics` com o bimestre inteiro para importar de uma só vez no calendário pessoal.

**Prioridade Média (Segurança e UI):**
- [ ] **Lixeira e Backups:** Substituir o `DELETE` direto no banco por um sistema de *soft delete* (lixeira) e backups automáticos do SQLite para evitar perdas de dados.
- [ ] **Filtros na Agenda:** Adicionar seletores rápidos por Turma e Disciplina na tela principal para limpar a visualização diária.
- [ ] **Status da Aula:** Indicadores visuais se a aula foi "Planejada", "Concluída", "Reposta" ou "Cancelada".

**Prioridade Baixa (Novas Funcionalidades):**
- [ ] **Suporte Multi-Escola:** A realidade do professor brasileiro envolve 2 a 3 escolas. O sistema será adaptado para alternar entre escolas sem poluir a interface, mantendo os dados isolados.
- [ ] **Busca Semântica BNCC:** Um modal reestruturado com as descrições completas da BNCC (tooltips) e uma barra de pesquisa que entenda contextos interdisciplinares.
- [ ] **Integração com IA:** Um botão para ler os parâmetros da aula (Turma, Data, Cód. BNCC) e gerar um prompt estruturado para o professor copiar e jogar no ChatGPT/Gemini, acelerando a escrita do roteiro metodológico.

## Como rodar localmente

Certifique-se de ter o Python 3.10+ instalado.

1. Clone o repositório:
```bash
git clone [https://github.com/seu-usuario/ClassPlanner.git](https://github.com/seu-usuario/ClassPlanner.git)
cd ClassPlanner

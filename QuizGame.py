# QuizGameApp.py
import sys
import json
import time
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QLineEdit, QRadioButton, QButtonGroup, QMessageBox,
    QHBoxLayout, QCheckBox, QScrollArea, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

QUESTIONS_FILE = "questions.json"

# ---------------- Helpers: load/save questions ----------------
def load_questions():
    try:
        with open(QUESTIONS_FILE, "r") as f:
            data = json.load(f)
            # ensure shape (13 questions)
            if not isinstance(data, list) or len(data) < 13:
                raise ValueError
            return data
    except Exception:
        default = []
        for i in range(13):
            default.append({
                "question": f"Question {i+1}",
                "answers": ["Answer A", "Answer B", "Answer C", "Answer D"],
                "correct": 0,
                "enabled": False
            })
        with open(QUESTIONS_FILE, "w") as f:
            json.dump(default, f, indent=4)
        return default

def save_questions(qs):
    with open(QUESTIONS_FILE, "w") as f:
        json.dump(qs, f, indent=4)

# ----------------- Main Menu -----------------
class MainMenu(QWidget):
    def __init__(self, stacked):
        super().__init__()
        self.stacked = stacked
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Quiz Buzzer Game")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:36px; font-weight:bold;")
        layout.addWidget(title)

        btn_start = QPushButton("Start")
        btn_start.setFixedSize(260, 80)
        btn_start.setStyleSheet("font-size:20px;")
        btn_start.clicked.connect(self.go_game)

        btn_edit = QPushButton("Edit Questions")
        btn_edit.setFixedSize(260, 80)
        btn_edit.setStyleSheet("font-size:20px;")
        btn_edit.clicked.connect(self.go_edit)

        layout.addSpacing(20)
        layout.addWidget(btn_start, alignment=Qt.AlignCenter)
        layout.addWidget(btn_edit, alignment=Qt.AlignCenter)
        self.setLayout(layout)

    def go_edit(self):
        self.stacked.setCurrentIndex(1)

    def go_game(self):
        self.stacked.widget(2).prepare_game()  # ensure questions loaded
        self.stacked.setCurrentIndex(2)

# ----------------- Question Editor -----------------
class QuestionEditor(QWidget):
    def __init__(self, stacked):
        super().__init__()
        self.stacked = stacked
        self.questions = load_questions()
        self.widgets = []  # list of tuples: (checkbox, qline, [(radio, aline), ...])

        layout = QVBoxLayout()
        layout.setContentsMargins(10,10,10,10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout()
        content.setLayout(content_layout)

        for i, q in enumerate(self.questions):
            block = QVBoxLayout()

            top = QHBoxLayout()
            chk = QCheckBox()
            chk.setChecked(q.get("enabled", False))
            top.addWidget(chk)

            qline = QLineEdit(q.get("question", ""))
            qline.setPlaceholderText("Type question here")
            qline.setStyleSheet("font-size:16px;")
            top.addWidget(QLabel(f"Q{i+1}:"))
            top.addWidget(qline)
            block.addLayout(top)

            ans_widgets = []
            radio_group = QButtonGroup(self)
            for j in range(4):
                row = QHBoxLayout()
                r = QRadioButton()
                radio_group.addButton(r, j)
                if j == q.get("correct", 0):
                    r.setChecked(True)
                aline = QLineEdit(q.get("answers", ["","","",""])[j] if "answers" in q else "")
                aline.setPlaceholderText(f"Answer {j+1}")
                aline.setStyleSheet("font-size:14px;")
                row.addWidget(r)
                row.addWidget(aline)
                block.addLayout(row)
                ans_widgets.append((r, aline))

            content_layout.addLayout(block)
            content_layout.addWidget(QLabel("—"*60))
            self.widgets.append((chk, qline, ans_widgets))

        scroll.setWidget(content)
        layout.addWidget(scroll)

        btns = QHBoxLayout()
        save_btn = QPushButton("Save Questions")
        save_btn.setStyleSheet("font-size:16px; padding:8px;")
        save_btn.clicked.connect(self.save)
        back_btn = QPushButton("Back")
        back_btn.setStyleSheet("font-size:16px; padding:8px;")
        back_btn.clicked.connect(self.back)
        btns.addWidget(save_btn)
        btns.addWidget(back_btn)
        layout.addLayout(btns)

        self.setLayout(layout)

    def save(self):
        qs = load_questions()  # start from file then update
        for i, (chk, qline, ans_widgets) in enumerate(self.widgets):
            qs[i]["enabled"] = bool(chk.isChecked())
            qs[i]["question"] = qline.text()
            qs[i]["answers"] = [aline.text() for _, aline in ans_widgets]
            # get correct radio
            for j, (r, _) in enumerate(ans_widgets):
                if r.isChecked():
                    qs[i]["correct"] = j
                    break
        save_questions(qs)
        QMessageBox.information(self, "Saved", "Questions saved to questions.json")

    def back(self):
        self.stacked.setCurrentIndex(0)

# ----------------- Game Page -----------------
class GamePage(QWidget):
    def __init__(self, stacked):
        super().__init__()
        self.stacked = stacked
        self.questions_all = []  # full list from file
        self.questions = []      # filtered enabled questions for this run
        self.current_q_index = -1

        # Player state
        self.num_players = 4
        self.scores = [0]*self.num_players
        self.active_players = [True]*self.num_players  # not greyed out for current question
        self.wrong_players = set()
        self.current_player = None  # index of the player who buzzed and must answer

        # Colors
        self.dark_colors = ["#660000", "#006600", "#000066", "#666600"]  # dark
        self.light_colors = ["#FF6666", "#66FF66", "#6666FF", "#FFFF66"]  # light
        self.grey = "#888888"

        # UI
        main = QVBoxLayout()
        main.setContentsMargins(12,12,12,12)

        # Player panels (showing score)
        self.player_labels = []
        ph = QHBoxLayout()
        for i in range(self.num_players):
            lbl = QLabel(f"P{i+1}: 0")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"background-color:{self.dark_colors[i]}; color: white; font-size:20px; padding:14px; border-radius:6px;")
            ph.addWidget(lbl)
            self.player_labels.append(lbl)
        main.addLayout(ph)
        main.addSpacing(12)

        # Question label
        self.q_label = QLabel("Press any buzzer to start")
        self.q_label.setAlignment(Qt.AlignCenter)
        self.q_label.setWordWrap(True)
        self.q_label.setStyleSheet("font-size:28px; font-weight:600;")
        main.addWidget(self.q_label)
        main.addSpacing(8)

        # Answer buttons
        self.answer_buttons = []
        for i in range(4):
            b = QPushButton(f"Answer {i+1}")
            b.setStyleSheet("font-size:22px; padding:14px;")
            b.clicked.connect(lambda checked, idx=i: self.player_answer(idx))
            b.setEnabled(False)
            main.addWidget(b)
            self.answer_buttons.append(b)

        # Control buttons (Back to menu)
        ctrl = QHBoxLayout()
        back = QPushButton("Back to Menu")
        back.setStyleSheet("font-size:16px;")
        back.clicked.connect(self.back_to_menu)
        ctrl.addWidget(back)
        main.addLayout(ctrl)

        self.setLayout(main)

        # Modbus client (sync)
        self.client = ModbusClient(method="rtu", port="/dev/ttyUSB0",
                                   baudrate=9600, parity='N', stopbits=1,
                                   bytesize=8, timeout=0.5)
        try:
            self.client.connect()
        except Exception as e:
            QMessageBox.critical(self, "Modbus Error", f"Could not connect to Modbus: {e}")

        # Timer to poll inputs (non-blocking)
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_buzzers)
        self.poll_timer.start(120)  # poll every 120 ms

    def prepare_game(self):
        # load questions and filter enabled ones
        self.questions_all = load_questions()
        self.questions = [q for q in self.questions_all if q.get("enabled", False)]
        if not self.questions:
            QMessageBox.warning(self, "No Questions", "No questions are enabled. Enable some in Edit Questions.")
            # still set label
            self.q_label.setText("No enabled questions. Edit questions to enable some.")
        self.current_q_index = -1
        self.scores = [0]*self.num_players
        self.active_players = [True]*self.num_players
        self.wrong_players.clear()
        self.current_player = None
        # refresh player panels
        for i, lbl in enumerate(self.player_labels):
            lbl.setText(f"P{i+1}: {self.scores[i]}")
            lbl.setStyleSheet(f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")
        self.q_label.setText("Press any buzzer to start")

    def back_to_menu(self):
        # stop any active question and go back
        self.current_player = None
        self.disable_answer_buttons()
        self.stacked.setCurrentIndex(0)

    def poll_buzzers(self):
        # if there's a current player answering, do not detect new buzzes
        if self.current_player is not None:
            return
        # read 4 discrete inputs starting at address 10 (this matches your PLC mapping)
        try:
            rr = self.client.read_discrete_inputs(10, 4, unit=1)
        except Exception:
            return
        if rr is None or hasattr(rr, "isError") and rr.isError():
            return
        bits = getattr(rr, "bits", None)
        if not bits:
            return
        # detect first pressed input where player is still active
        for i, pressed in enumerate(bits):
            if pressed and self.active_players[i]:
                # set current player
                self.current_player = i
                # highlight player lighter
                self.player_labels[i].setStyleSheet(
                    f"background-color:{self.light_colors[i]}; color:black; font-size:20px; padding:14px; border-radius:6px;")
                # enable answers for this player
                for b in self.answer_buttons:
                    b.setEnabled(True)
                # if this is the first press in the round, load next question (advance)
                if self.current_q_index == -1 or all(btn.isEnabled() == False for btn in self.answer_buttons):
                    # if no active question, ask next
                    self.next_question()
                break

    def next_question(self):
        # move to next question in filtered list
        self.current_q_index += 1
        # skip questions with empty text if any
        while self.current_q_index < len(self.questions) and not self.questions[self.current_q_index].get("question"):
            self.current_q_index += 1
        if self.current_q_index >= len(self.questions):
            self.end_game()
            return
        q = self.questions[self.current_q_index]
        self.q_label.setText(q.get("question", ""))
        for i, b in enumerate(self.answer_buttons):
            b.setText(q.get("answers", ["","","",""])[i])
            b.setEnabled(True)

    def disable_answer_buttons(self):
        for b in self.answer_buttons:
            b.setEnabled(False)

    def player_answer(self, answer_idx):
        # current_player answered by clicking answer_idx
        if self.current_player is None:
            return
        q = self.questions[self.current_q_index]
        correct = q.get("correct", 0)
        player = self.current_player
        if answer_idx == correct:
            # correct answer
            if len(self.wrong_players) == 0:
                self.scores[player] += 100
            else:
                self.scores[player] += 50
            # update display
            self.player_labels[player].setText(f"P{player+1}: {self.scores[player]}")
            # clear states and go to next question
            self.reset_round_visuals()
            self.current_player = None
            self.disable_answer_buttons()
            # next question will be asked on next buzz; optionally auto-advance:
            # auto-advance immediate:
            self.next_question()
        else:
            # wrong answer -> grey out player for this question
            self.wrong_players.add(player)
            self.active_players[player] = False
            self.player_labels[player].setStyleSheet(
                f"background-color:{self.grey}; color:black; font-size:20px; padding:14px; border-radius:6px;")
            # disable answering for this player now; allow others (clear current_player so others can buzz)
            self.current_player = None
            self.disable_answer_buttons()
            # if all players wrong, reveal correct and move on
            if all(not ap for ap in self.active_players):
                QMessageBox.information(self, "No one left", "All players missed this question. Moving to next.")
                self.reset_round_visuals()
                self.next_question()

    def reset_round_visuals(self):
        # reset player visuals but keep scores; re-enable all active_players for next round
        self.active_players = [True]*self.num_players
        self.wrong_players.clear()
        for i in range(self.num_players):
            self.player_labels[i].setStyleSheet(
                f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")
            self.player_labels[i].setText(f"P{i+1}: {self.scores[i]}")
        self.disable_answer_buttons()

    def end_game(self):
        # pick winner by highest score (tie: first max index)
        if not any(q.get("enabled", False) for q in load_questions()):
            QMessageBox.information(self, "Game Over", "No enabled questions were found.")
            self.back_to_menu()
            return
        if sum(self.scores) == 0:
            # nobody scored
            QMessageBox.information(self, "Game Over", "Game finished. No points scored.")
        else:
            max_score = max(self.scores)
            winners = [i for i, s in enumerate(self.scores) if s == max_score]
            if len(winners) == 1:
                w = winners[0]
                QMessageBox.information(self, "Game Over", f"🎉 Player {w+1} wins with {max_score} points!")
            else:
                # tie - list winners
                names = ", ".join(f"P{i+1}" for i in winners)
                QMessageBox.information(self, "Game Over", f"Tie! Winners: {names} with {max_score} points each.")
        # reset game state and go to menu
        self.prepare_game()
        self.stacked.setCurrentIndex(0)

# ----------------- Application start -----------------
def main():
    app = QApplication(sys.argv)
    stacked = QStackedWidget()

    main_menu = MainMenu(stacked)
    editor = QuestionEditor(stacked)
    game = GamePage(stacked)

    stacked.addWidget(main_menu)  # index 0
    stacked.addWidget(editor)     # index 1
    stacked.addWidget(game)       # index 2

    stacked.setFixedSize(1000, 700)
    stacked.setWindowTitle("QuizGame App")
    stacked.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

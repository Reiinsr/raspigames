import sys
import json
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QLineEdit, QRadioButton, QButtonGroup, QMessageBox,
    QHBoxLayout, QCheckBox, QScrollArea, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

QUESTIONS_FILE = "questions.json"

# ---------- Helpers: load/save questions ----------
def load_questions():
    try:
        with open(QUESTIONS_FILE, "r") as f:
            data = json.load(f)
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

# ---------- Main Menu ----------
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
        self.stacked.widget(2).prepare_game()
        self.stacked.setCurrentIndex(2)

# ---------- Question Editor ----------
class QuestionEditor(QWidget):
    def __init__(self, stacked):
        super().__init__()
        self.stacked = stacked
        self.questions = load_questions()
        self.widgets = []

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

            top.addWidget(QLabel(f"Q{i+1}:"))
            qline = QLineEdit(q.get("question", ""))
            qline.setPlaceholderText("Type question here")
            qline.setStyleSheet("font-size:16px;")
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
        qs = load_questions()
        for i, (chk, qline, ans_widgets) in enumerate(self.widgets):
            qs[i]["enabled"] = bool(chk.isChecked())
            qs[i]["question"] = qline.text()
            qs[i]["answers"] = [aline.text() for _, aline in ans_widgets]
            for j, (r, _) in enumerate(ans_widgets):
                if r.isChecked():
                    qs[i]["correct"] = j
                    break
        save_questions(qs)
        QMessageBox.information(self, "Saved", "Questions saved to questions.json")

    def back(self):
        self.stacked.setCurrentIndex(0)

# ---------- Game Page ----------
class GamePage(QWidget):
    def __init__(self, stacked):
        super().__init__()
        self.stacked = stacked
        self.questions_all = []
        self.questions = []
        self.current_q_index = -1

        # Players & state
        self.num_players = 4
        self.scores = [0]*self.num_players
        self.active_players = [True]*self.num_players
        self.wrong_players = set()
        self.current_player = None
        self.manual_winner_mode = False

        # Colors
        self.dark_colors = ["#660000", "#006600", "#000066", "#666600"]  # dark
        self.light_colors = ["#FF6666", "#66FF66", "#6666FF", "#FFFF66"]  # light
        self.grey = "#888888"

        # UI layout
        main = QVBoxLayout()
        main.setContentsMargins(12,12,12,12)

        # Player panels with scores
        self.player_labels = []
        ph = QHBoxLayout()
        for i in range(self.num_players):
            lbl = QLabel(f"P{i+1}: 0")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"background-color:{self.dark_colors[i]}; color: white; font-size:20px; padding:14px; border-radius:6px;")
            lbl.mousePressEvent = lambda event, idx=i: self.manual_pick(idx)
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

        # Answer buttons (up to 4, will hide unused)
        self.answer_buttons = []
        for i in range(4):
            b = QPushButton(f"Answer {i+1}")
            b.setStyleSheet("font-size:22px; padding:14px;")
            b.clicked.connect(lambda checked, idx=i: self.player_answer(idx))
            b.setEnabled(False)
            main.addWidget(b)
            self.answer_buttons.append(b)

        # Controls
        ctrl = QHBoxLayout()
        back = QPushButton("Back to Menu")
        back.setStyleSheet("font-size:16px;")
        back.clicked.connect(self.back_to_menu)
        ctrl.addWidget(back)
        main.addLayout(ctrl)

        self.setLayout(main)

        # Modbus client
        self.client = ModbusClient(method="rtu", port="/dev/ttyUSB0",
                                   baudrate=9600, parity='N', stopbits=1,
                                   bytesize=8, timeout=0.5)
        try:
            self.client.connect()
        except Exception:
            QMessageBox.critical(self, "Modbus Error", "Could not connect to Modbus/PLC. Make sure /dev/ttyUSB0 is correct.")

        # Poll timer
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_buzzers)
        self.poll_timer.start(120)

        # Winner overlay + blink timer placeholders
        self.overlay = None
        self.winner_label = None
        self.blink_timer = None
        self.blink_state = False
        self.final_winner_indices = []

    def prepare_game(self):
        self.questions_all = load_questions()
        self.questions = [q for q in self.questions_all if q.get("enabled", False)]
        self.current_q_index = -1
        self.scores = [0]*self.num_players
        self.active_players = [True]*self.num_players
        self.wrong_players.clear()
        self.current_player = None
        self.manual_winner_mode = False
        self.next_question()

    def next_question(self):
        self.current_q_index +=1
        if self.current_q_index >= len(self.questions):
            self.game_over()
            return
        self.q_label.setText(self.questions[self.current_q_index]["question"])
        self.wrong_players.clear()
        self.current_player = None

        # Setup answers, skip blanks
        qdata = self.questions[self.current_q_index]
        nonblank = [(i,a) for i,a in enumerate(qdata["answers"]) if a.strip() != ""]
        if len(nonblank)==0:
            self.q_label.setText("Host: No answers defined. Click a winner above!")
            self.manual_winner_mode = True
            for b in self.answer_buttons:
                b.hide()
        else:
            self.manual_winner_mode = False
            for idx, btn in enumerate(self.answer_buttons):
                if idx < len(nonblank):
                    btn.setText(nonblank[idx][1])
                    btn.setEnabled(True)
                    btn.show()
                else:
                    btn.hide()
            self.correct_mapping = {i:nonblank[i][0] for i in range(len(nonblank))}

        # Reset player colors
        for i,lbl in enumerate(self.player_labels):
            color = self.dark_colors[i] if self.active_players[i] else self.grey
            lbl.setStyleSheet(f"background-color:{color}; color:white; font-size:20px; padding:14px; border-radius:6px;")

        # Hide overlay if exists
        if self.overlay:
            self.overlay.hide()
        if self.winner_label:
            self.winner_label.hide()
        if self.blink_timer:
            self.blink_timer.stop()

    def poll_buzzers(self):
        if self.manual_winner_mode or not self.client:
            return
        try:
            rr = self.client.read_discrete_inputs(10, 4, unit=1)
            if rr.isError():
                return
            for i, pressed in enumerate(rr.bits):
                if pressed and self.current_player is None and self.active_players[i]:
                    self.current_player = i
                    self.highlight_player(i)
        except Exception:
            pass

    def highlight_player(self, idx):
        self.player_labels[idx].setStyleSheet(f"background-color:{self.light_colors[idx]}; color:white; font-size:20px; padding:14px; border-radius:6px;")

    def player_answer(self, answer_idx):
        if self.current_player is None:
            return
        real_idx = self.correct_mapping[answer_idx]
        correct = self.questions[self.current_q_index]["correct"]
        if real_idx == correct:
            if self.wrong_players:
                self.scores[self.current_player] +=50
            else:
                self.scores[self.current_player] +=100
            self.player_labels[self.current_player].setText(f"P{self.current_player+1}: {self.scores[self.current_player]}")
            self.next_question()
        else:
            self.active_players[self.current_player] = False
            self.wrong_players.add(self.current_player)
            self.player_labels[self.current_player].setStyleSheet(f"background-color:{self.grey}; color:white; font-size:20px; padding:14px; border-radius:6px;")
            self.current_player = None

    def manual_pick(self, idx):
        if self.manual_winner_mode:
            self.final_winner_indices = [idx]
            self.display_final_winner()

    def game_over(self):
        max_score = max(self.scores)
        winners = [i for i,s in enumerate(self.scores) if s == max_score]
        self.final_winner_indices = winners
        self.display_final_winner()

    def display_final_winner(self):
        if self.overlay:
            self.overlay.hide()
        if self.winner_label:
            self.winner_label.hide()

        self.overlay = QLabel("GAME OVER", self)
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setStyleSheet("font-size:64px; font-weight:bold; color:black; background-color: rgba(0,0,0,0);")
        self.overlay.setGeometry(0,180,self.width(),200)
        self.overlay.show()

        winner_names = ", ".join([f"P{i+1}" for i in self.final_winner_indices])
        self.winner_label = QLabel(f"{winner_names} is the Winner!", self)
        self.winner_label.setAlignment(Qt.AlignCenter)
        self.winner_label.setStyleSheet("font-size:40px; font-weight:bold; color:black; background-color: rgba(0,0,0,0);")
        self.winner_label.setGeometry(0,350,self.width(),100)
        self.winner_label.show()

        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.blink_winners)
        self.blink_timer.start(500)

    def blink_winners(self):
        self.blink_state = not self.blink_state
        for i in range(self.num_players):
            if i in self.final_winner_indices:
                color = self.light_colors[i] if self.blink_state else self.dark_colors[i]
                self.player_labels[i].setStyleSheet(f"background-color:{color}; color:white; font-size:20px; padding:14px; border-radius:6px;")

    def back_to_menu(self):
        self.stacked.setCurrentIndex(0)

# ---------- Main ----------
if __name__=="__main__":
    app = QApplication(sys.argv)
    stacked = QStackedWidget()

    main_menu = MainMenu(stacked)
    editor = QuestionEditor(stacked)
    game = GamePage(stacked)

    stacked.addWidget(main_menu)
    stacked.addWidget(editor)
    stacked.addWidget(game)

    stacked.setFixedSize(1000,700)
    stacked.show()

    sys.exit(app.exec())

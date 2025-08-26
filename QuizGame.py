import sys
import threading
import time
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QLineEdit, QRadioButton, QButtonGroup,
    QMessageBox, QStackedLayout, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

# ---- Modbus setup ----
client = ModbusClient(
    method="rtu",
    port="/dev/ttyUSB0",  # change if needed
    baudrate=9600,
    parity="N",
    stopbits=1,
    bytesize=8,
    timeout=1
)

if not client.connect():
    print("Could not connect to PLC")
    exit()

running = True
winner = None
current_question_index = 0
num_players = 4
active_players = [True]*num_players
scores = [0]*num_players

# ---- Colors ----
player_colors = ["#660000", "#006600", "#000066", "#666600"]  # dark
winner_colors = ["#FF6666", "#66FF66", "#6666FF", "#FFFF66"]  # light
grey_color = "#888888"

# ---- Questions file ----
QUESTION_FILE = "questions.json"

# ---- Load or create questions ----
try:
    with open(QUESTION_FILE, "r") as f:
        questions = json.load(f)
except:
    # default empty questions
    questions = [{"question": f"Question {i+1}", "answers": ["A","B","C","D"], "correct":0} for i in range(13)]
    with open(QUESTION_FILE, "w") as f:
        json.dump(questions, f, indent=4)

# ---- Background thread to poll PLC ----
def poll_modbus():
    global winner
    while running:
        if winner is None:
            rr = client.read_discrete_inputs(10, 16, unit=1)  # X0-X3
            if not rr.isError():
                inputs = rr.bits
                for i, pressed in enumerate(inputs):
                    if pressed and winner is None:
                        winner = i
                        break
        time.sleep(0.1)

# ---- Main Application ----
class QuizApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quiz Game")
        self.resize(900, 600)
        self.stack = QStackedLayout()

        container = QWidget()
        container.setLayout(self.stack)
        self.setCentralWidget(container)

        self.main_menu = self.create_main_menu()
        self.editor_page = self.create_editor_page()
        self.game_page = self.create_game_page()

        self.stack.addWidget(self.main_menu)
        self.stack.addWidget(self.editor_page)
        self.stack.addWidget(self.game_page)

        # Timer for GUI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_game)
        self.timer.start(100)

    # ---- Main Menu ----
    def create_main_menu(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        start_btn = QPushButton("Start")
        start_btn.setFixedSize(200, 80)
        start_btn.clicked.connect(self.start_game)

        edit_btn = QPushButton("Edit Questions")
        edit_btn.setFixedSize(200, 80)
        edit_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.editor_page))

        layout.addWidget(start_btn)
        layout.addWidget(edit_btn)
        page.setLayout(layout)
        return page

    # ---- Question Editor Page ----
    def create_editor_page(self):
        page = QWidget()
        layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()

        self.edit_fields = []
        for idx, q in enumerate(questions):
            q_layout = QVBoxLayout()
            q_label = QLabel(f"Question {idx+1}")
            q_text = QLineEdit(q["question"])
            answer_fields = []
            correct_group = QButtonGroup()
            for i in range(4):
                ans_layout = QHBoxLayout()
                radio = QRadioButton()
                if i == q["correct"]:
                    radio.setChecked(True)
                txt = QLineEdit(q["answers"][i])
                ans_layout.addWidget(radio)
                ans_layout.addWidget(txt)
                q_layout.addLayout(ans_layout)
                correct_group.addButton(radio, i)
                answer_fields.append((txt, radio))
            self.edit_fields.append((q_text, answer_fields))
            scroll_layout.addLayout(q_layout)
            scroll_layout.addWidget(QLabel("--------"))
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        save_btn = QPushButton("Save Questions")
        save_btn.clicked.connect(self.save_questions)
        layout.addWidget(save_btn)

        page.setLayout(layout)
        return page

    # ---- Save Questions ----
    def save_questions(self):
        global questions
        for idx, (q_text, ans_fields) in enumerate(self.edit_fields):
            questions[idx]["question"] = q_text.text()
            questions[idx]["answers"] = [txt.text() for txt, _ in ans_fields]
            for i, (_, radio) in enumerate(ans_fields):
                if radio.isChecked():
                    questions[idx]["correct"] = i
                    break
        with open(QUESTION_FILE, "w") as f:
            json.dump(questions, f, indent=4)
        QMessageBox.information(self, "Saved", "Questions saved successfully!")

    # ---- Game Page ----
    def create_game_page(self):
        page = QWidget()
        self.question_label = QLabel("", self)
        self.question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_label.setWordWrap(True)
        self.answer_buttons = []
        answer_layout = QVBoxLayout()
        for i in range(4):
            btn = QPushButton("")
            btn.setFixedHeight(50)
            btn.clicked.connect(lambda checked, b=i: self.check_answer(b))
            self.answer_buttons.append(btn)
            answer_layout.addWidget(btn)

        # Player panels
        self.player_labels = []
        player_layout = QHBoxLayout()
        for i in range(num_players):
            lbl = QLabel(f"Player {i+1}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:18px; padding:20px; border:1px solid black; background-color:{player_colors[i]}; color:white;")
            self.player_labels.append(lbl)
            player_layout.addWidget(lbl)

        layout = QVBoxLayout()
        layout.addWidget(self.question_label)
        layout.addLayout(answer_layout)
        layout.addLayout(player_layout)
        page.setLayout(layout)
        return page

    def start_game(self):
        self.stack.setCurrentWidget(self.game_page)
        self.load_question()

    def load_question(self):
        global current_question_index, active_players
        q = questions[current_question_index]
        self.question_label.setText(q["question"])
        for i, btn in enumerate(self.answer_buttons):
            btn.setText(q["answers"][i])
            btn.setEnabled(False)
        active_players = [True]*num_players
        for i, lbl in enumerate(self.player_labels):
            lbl.setStyleSheet(f"font-size:18px; padding:20px; border:1px solid black; background-color:{player_colors[i]}; color:white;")

    def update_game(self):
        global winner
        if winner is not None:
            # enable answer buttons for the winner only
            for i, btn in enumerate(self.answer_buttons):
                btn.setEnabled(True)

    def check_answer(self, answer_idx):
        global winner, current_question_index, scores, active_players
        q = questions[current_question_index]
        if winner is None:
            return
        player_idx = winner
        if answer_idx == q["correct"]:
            # correct answer
            if sum(active_players) == num_players:
                scores[player_idx] += 100  # first correct
            else:
                scores[player_idx] += 50  # after first lost
            current_question_index += 1
            winner = None
            if current_question_index >= len(questions):
                QMessageBox.information(self, "Game Over", "All questions finished!")
                current_question_index = 0
            self.load_question()
        else:
            # wrong answer, grey out player
            active_players[player_idx] = False
            self.player_labels[player_idx].setStyleSheet(f"font-size:18px; padding:20px; border:1px solid black; background-color:{grey_color}; color:white;")
            winner = None

    def keyPressEvent(self, event):
        """Reset round with Enter if needed"""
        global winner
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            winner = None
            self.load_question()


if __name__ == "__main__":
    threading.Thread(target=poll_modbus, daemon=True).start()
    app = QApplication(sys.argv)
    quiz = QuizApp()
    quiz.show()
    sys.exit(app.exec())
    running = False
    client.close()

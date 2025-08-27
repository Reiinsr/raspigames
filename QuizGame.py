# QuizGameApp.py
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
        self.blink_timer = None
        self.blink_state = False
        self.final_winner_indices = []

    def prepare_game(self):
        self.questions_all = load_questions()
        self.questions = [q for q in self.questions_all if q.get("enabled", False)]
        if not self.questions:
            QMessageBox.warning(self, "No Questions", "No questions are enabled. Enable some in Edit Questions.")
            self.q_label.setText("No enabled questions. Edit questions to enable some.")
        self.current_q_index = -1
        self.scores = [0]*self.num_players
        self.active_players = [True]*self.num_players
        self.wrong_players.clear()
        self.current_player = None
        for i, lbl in enumerate(self.player_labels):
            lbl.setText(f"P{i+1}: {self.scores[i]}")
            lbl.setStyleSheet(f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")
        self.q_label.setText("Press any buzzer to start")

    def back_to_menu(self):
        self.current_player = None
        self.disable_answer_buttons()
        # stop blink timers if any
        self.stop_blinking()
        self.hide_overlay()
        self.stacked.setCurrentIndex(0)

    def poll_buzzers(self):
        if self.current_player is not None:
            return
        try:
            rr = self.client.read_discrete_inputs(10, 4, unit=1)
        except Exception:
            return
        if rr is None or (hasattr(rr, "isError") and rr.isError()):
            return
        bits = getattr(rr, "bits", None)
        if not bits:
            return
        for i, pressed in enumerate(bits):
            if pressed and self.active_players[i]:
                self.current_player = i
                # highlight player
                self.player_labels[i].setStyleSheet(
                    f"background-color:{self.light_colors[i]}; color:black; font-size:20px; padding:14px; border-radius:6px;")
                for b in self.answer_buttons:
                    b.setEnabled(True)
                # if no question loaded yet, load next
                if self.current_q_index == -1 or all(not btn.isEnabled() for btn in self.answer_buttons):
                    self.next_question()
                break

    def next_question(self):
        self.current_q_index += 1
        # skip empty questions
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
        if self.current_player is None:
            return
        q = self.questions[self.current_q_index]
        correct = q.get("correct", 0)
        player = self.current_player
        if answer_idx == correct:
            # correct
            if len(self.wrong_players) == 0:
                self.scores[player] += 100
            else:
                self.scores[player] += 50
            self.player_labels[player].setText(f"P{player+1}: {self.scores[player]}")
            # reset visuals and go to next
            self.reset_round_visuals()
            self.current_player = None
            self.disable_answer_buttons()
            # auto-advance to next question immediately
            self.next_question()
        else:
            # wrong answer
            self.wrong_players.add(player)
            self.active_players[player] = False
            self.player_labels[player].setStyleSheet(
                f"background-color:{self.grey}; color:black; font-size:20px; padding:14px; border-radius:6px;")
            self.current_player = None
            self.disable_answer_buttons()
            if all(not ap for ap in self.active_players):
                QMessageBox.information(self, "No one left", "All players missed this question. Moving to next.")
                self.reset_round_visuals()
                self.next_question()

    def reset_round_visuals(self):
        self.active_players = [True]*self.num_players
        self.wrong_players.clear()
        for i in range(self.num_players):
            self.player_labels[i].setStyleSheet(
                f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")
            self.player_labels[i].setText(f"P{i+1}: {self.scores[i]}")
        self.disable_answer_buttons()

    def end_game(self):
        # determine winner(s)
        if not any(q.get("enabled", False) for q in load_questions()):
            QMessageBox.information(self, "Game Over", "No enabled questions were found.")
            self.prepare_game()
            self.stacked.setCurrentIndex(0)
            return

        if all(score == 0 for score in self.scores):
            QMessageBox.information(self, "Game Over", "Game finished. No points scored.")
            self.prepare_game()
            self.stacked.setCurrentIndex(0)
            return

        max_score = max(self.scores)
        winners = [i for i, s in enumerate(self.scores) if s == max_score]
        self.final_winner_indices = winners  # could be multiple

        # Show blinking + huge GAME OVER overlay
        self.show_winner_effect()

    def show_winner_effect(self):
        # stop polling new buzzes
        self.poll_timer_stop()
        # overlay
        if self.overlay is None:
            self.overlay = QWidget(self)
            self.overlay.setAttribute(Qt.WA_StyledBackground, True)
            self.overlay.setStyleSheet("background-color: rgba(0,0,0,160);")
            self.overlay.setGeometry(0, 0, self.width(), self.height())

            v = QVBoxLayout(self.overlay)
            v.setAlignment(Qt.AlignCenter)

            self.game_over_label = QLabel("GAME OVER")
            self.game_over_label.setAlignment(Qt.AlignCenter)
            self.game_over_label.setStyleSheet("font-size:72px; font-weight:bold; color: white;")
            v.addWidget(self.game_over_label)

            # show winner text (if tie, show multiple)
            if len(self.final_winner_indices) == 1:
                w = self.final_winner_indices[0]
                winner_text = f"Winner: Player {w+1}\nScore: {self.scores[w]}"
            else:
                names = ", ".join(f"P{i+1}" for i in self.final_winner_indices)
                winner_text = f"Tie between: {names}\nScore: {self.scores[self.final_winner_indices[0]]}"
            self.winner_label = QLabel(winner_text)
            self.winner_label.setAlignment(Qt.AlignCenter)
            self.winner_label.setStyleSheet("font-size:28px; color: white;")
            v.addWidget(self.winner_label)

            # Return button
            btn = QPushButton("Return to Menu")
            btn.setStyleSheet("font-size:20px; padding:12px;")
            btn.clicked.connect(self.return_to_menu_from_overlay)
            v.addWidget(btn)

        self.overlay.show()
        # start blinking winner labels
        self.blink_state = False
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.blink_winner_labels)
        self.blink_timer.start(500)  # toggle every 500ms

    def blink_winner_labels(self):
        # toggle colors for winners
        self.blink_state = not self.blink_state
        for i in range(self.num_players):
            if i in self.final_winner_indices:
                if self.blink_state:
                    # lighter color
                    self.player_labels[i].setStyleSheet(
                        f"background-color:{self.light_colors[i]}; color:black; font-size:20px; padding:14px; border-radius:6px;")
                else:
                    # dark color
                    self.player_labels[i].setStyleSheet(
                        f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")
            else:
                # ensure others stay dark (not blinking)
                self.player_labels[i].setStyleSheet(
                    f"background-color:{self.dark_colors[i]}; color:white; font-size:20px; padding:14px; border-radius:6px;")

    def poll_timer_stop(self):
        if self.poll_timer.isActive():
            self.poll_timer.stop()

    def poll_timer_start(self):
        if not self.poll_timer.isActive():
            self.poll_timer.start(120)

    def stop_blinking(self):
        if self.blink_timer:
            self.blink_timer.stop()
            self.blink_timer = None

    def hide_overlay(self):
        if self.overlay:
            self.overlay.hide()

    def return_to_menu_from_overlay(self):
        # stop blinking and hide overlay, reset and go to menu
        self.stop_blinking()
        self.hide_overlay()
        self.prepare_game()
        self.stacked.setCurrentIndex(0)
        # restart polling
        self.poll_timer_start()

    def keyPressEvent(self, event):
        # allow Enter to reset or to return when overlay visible
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.overlay and self.overlay.isVisible():
                self.return_to_menu_from_overlay()
            else:
                # reset current question round if needed
                self.current_player = None
                self.disable_answer_buttons()
                self.reset_round_visuals()

# ---------- Application entry ----------
def main():
    app = QApplication(sys.argv)
    stacked = QStackedWidget()

    main_menu = MainMenu(stacked)
    editor = QuestionEditor(stacked)
    game = GamePage(stacked)

    stacked.addWidget(main_menu)  # 0
    stacked.addWidget(editor)     # 1
    stacked.addWidget(game)       # 2

    stacked.setFixedSize(1000, 700)
    stacked.setWindowTitle("QuizGame App")
    stacked.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

import sys
import json
from tkinter import *
from tkinter.ttk import *
from tkinter.messagebox import *
import threading
import queue
import pathlib
import requests
from bs4 import BeautifulSoup
from pygame import mixer
import schedule
import paramiko
import chardet
from loguru import logger

logger.remove()
logger.add("record_{time:YYYY-MM-DD}.log", retention="3 days")  # Cleanup after some time

task_queue = queue.Queue(1000)


class SshPut:
    def __init__(self):
        with open("config.json", encoding="utf-8") as fp:
            data = json.load(fp)
        self.data = data

    def put(self, filename):
        logger.info("send file: %s", str(filename))
        t = paramiko.Transport(self.data['hostname'], self.data["port"])
        t.connect(username=self.data["username"], password=self.data["password"])
        sftp = paramiko.SFTPClient.from_transport(t)
        new_file = filename.rename(filename.parent / "upload" / filename.name)
        sftp.put(localpath=filename, remotepath=new_file)
        t.close()
        self.run_cmd(filename)

    def run_cmd(self, filename):
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.connect(self.data["hostname"], self.data["port"], self.data["username"], password=self.data["password"])
        stdin, stdout, stderr = s.exec_command(f"cmd /c call {filename}")
        s.close()
        if text := (stdout.read() + stderr.read()):
            if encoding := chardet.detect(text):
                logger.info("remote command execute result: %s", text.decode(encoding["encoding"]))


def center_window(win, w, h):
    ws = win.winfo_screenwidth()
    hs = win.winfo_screenheight()
    x = (ws / 2) - (w / 2)
    y = (hs / 2) - (h / 2)
    win.geometry('%dx%d+%d+%d' % (w, h, x, y))


def parse(html):
    import lxml
    soup = BeautifulSoup(html, "lxml")
    tbody = soup.find("tbody")
    data = []
    for tr in tbody.find_all("tr", class_=True):
        row = [t.get_text(strip=True) for t in tr.find_all("td")]
        data.append(row)
    abnormal = [row for row in data if row[-1] != "异常"]
    return abnormal


def request_html():
    with open("config.json", encoding="utf-8") as fp:
        data = json.load(fp)
    logger.info("检测任务开始执行")
    return requests.get(
        url=data["check_url"],
        headers={
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
        }
    ).text


def find_file(suffix=".bat"):
    files = [path for path in pathlib.Path(__file__).parent.glob("*" + suffix)]
    if files:
        return files[0]
    showerror("错误", f"没有在到:{suffix}文件")
    sys.exit()


class App(Tk):
    def __init__(self):
        super().__init__()
        center_window(self, 300, 280)
        self.bat = find_file(".bat")
        self.wav = find_file(".wav")
        mixer.music.load(self.wav)
        self.tips = StringVar()
        self.message = StringVar()
        Label(self, textvariable=self.message, foreground="orange").place(x=10, y=10)
        Label(self, textvariable=self.tips, justify=CENTER, foreground="red").pack(side=TOP, pady=50)
        Button(self, text="确认", command=self.sure).pack(side=TOP, pady=25)
        self.task = schedule.every(60).seconds.tag("main").do(self.task_func)
        self.event_loop()
        self.show_window = threading.Event()

    def event_loop(self):
        schedule.run_pending()
        self.after(1, self.event_loop)

    def sure(self):
        mixer.music.stop()
        self.withdraw()
        self.show_window.set()

    @staticmethod
    def task_func():
        html = request_html()
        for row in parse(html):
            logger.info("%s 异常", row[3])
            task_queue.put(row)

    def execute_task(self):
        while True:
            try:
                row = task_queue.get(block=True)
            except queue.Empty:
                pass
            else:
                name = row[3]
                self.message.set(f"剩余待处理异常: {task_queue.qsize()}")
                text = f"请注意\n{name}\n设备状态异常"
                self.tips.set(text)
                SshPut().put(self.bat.absolute())
                self.wm_deiconify()
                mixer.music.play()
                logger.info("%s 异常等待确认", name)
                self.show_window.wait()
                logger.info("%s 异常确认完成", name)
                task_queue.task_done()
                self.show_window.clear()


if __name__ == '__main__':
    logger.info("程序开始运行")
    mixer.init()
    app = App()
    app.wm_iconify()
    thread = threading.Thread(target=app.execute_task)
    thread.daemon = True
    thread.start()
    app.mainloop()

import tkinter as tk
from tkinter import ttk
import requests
import json


DEFAULT_START_JSON = """{
    "gmcode": "Ball3_HTTP_TEST",
    "gmstate": 1,
    "table": "B001",
    "deviceId": "obs",
    "streamId": "OBS233jk"
}"""

DEFAULT_STOP_JSON = """{
    "gmcode": "Ball3_HTTP_TEST",
    "gmstate": 0,
    "table": "B001",
    "deviceId": "obs",
    "streamId": "OBS233jk"
}"""

class HttpTester:

    def __init__(self, root):

        self.root = root
        root.title("BALL3 HTTP Integration Test")

        main = ttk.Frame(root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # URL
        ttk.Label(main, text="URL").grid(row=0, column=0, sticky="w")

        self.url = tk.StringVar(value="http://127.0.0.1:9000/start_predict")

        ttk.Entry(main, textvariable=self.url, width=60).grid(
            row=0, column=1, columnspan=3, sticky="we"
        )

        # Method
        ttk.Label(main, text="Method").grid(row=1, column=0, sticky="w")

        self.method = tk.StringVar(value="POST")

        ttk.Radiobutton(main, text="GET", value="GET", variable=self.method).grid(row=1, column=1)
        ttk.Radiobutton(main, text="POST", value="POST", variable=self.method).grid(row=1, column=2)

        # JSON
        ttk.Label(main, text="JSON Body").grid(row=2, column=0, sticky="nw")

        self.json_text = tk.Text(main, height=10, width=60)
        self.json_text.grid(row=2, column=1, columnspan=3)

        self.json_text.insert("1.0", DEFAULT_START_JSON)

        # Buttons
        ttk.Button(main, text="Load START", command=self.load_start).grid(row=3, column=1)
        ttk.Button(main, text="Load STOP", command=self.load_stop).grid(row=3, column=2)
        ttk.Button(main, text="Send Request", command=self.send_request).grid(row=3, column=3)

        # Response
        ttk.Label(main, text="Response").grid(row=4, column=0, sticky="nw")

        self.response = tk.Text(main, height=12, width=60)
        self.response.grid(row=4, column=1, columnspan=3)

    def load_start(self):

        self.url.set("http://127.0.0.1:9000/start_predict")

        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", DEFAULT_START_JSON)

    def load_stop(self):

        self.url.set("http://127.0.0.1:9000/stop_predict")

        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", DEFAULT_STOP_JSON)

    def send_request(self):

        url = self.url.get()
        method = self.method.get()

        body = self.json_text.get("1.0", tk.END)

        try:

            data = json.loads(body)

            if method == "POST":

                r = requests.post(url, json=data)

            else:

                r = requests.get(url, params=data)

            result = f"Status: {r.status_code}\n\n{r.text}"

        except Exception as e:

            result = str(e)

        self.response.delete("1.0", tk.END)
        self.response.insert("1.0", result)


if __name__ == "__main__":

    root = tk.Tk()

    HttpTester(root)

    root.mainloop()
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import threading
import queue
import socket
import json
from http.server import SimpleHTTPRequestHandler, HTTPServer
import time # For simulation of time passing in server

# --- Shared Data Store for Timer State ---
# This dictionary will hold the current state of the timer, accessible by both threads.
# A lock is used to prevent race conditions when updating/reading this shared data.
timer_state = {
    "time_text": "00:00",
    "speaker_name": "N/A",
    "speaker_segment": "N/A",
    "is_warning": False,
    "is_past_zero": False
}
timer_state_lock = threading.Lock()

# --- Custom HTTP Request Handler ---
class TimerRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/timer_state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*') # Allow CORS for mobile client
            self.end_headers()
            
            with timer_state_lock:
                response_data = json.dumps(timer_state)
            self.wfile.write(response_data.encode('utf-8'))
        else:
            # For any other path, return a 404 for simplicity if we only want to serve /timer_state
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')

    def log_message(self, format, *args):
        # Suppress logging HTTP requests to console to avoid clutter
        pass

# --- HTTP Server Thread ---
class HttpServerThread(threading.Thread):
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.httpd = None
        self.running = False

    def run(self):
        self.running = True
        server_address = (self.host, self.port)
        self.httpd = HTTPServer(server_address, TimerRequestHandler)
        print(f"HTTP Server: Started on http://{self.host}:{self.port}")
        try:
            self.httpd.serve_forever()
        except Exception as e:
            print(f"HTTP Server: Error serving: {e}")
        finally:
            print("HTTP Server: Shutting down.")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.running = False


# --- Class for the Speaker Display Window ---
class SpeakerDisplayWindow(tk.Toplevel):
    def __init__(self, master):
        """
        Initializes the dedicated speaker display window with enhanced styling.
        """
        super().__init__(master)
        print("SpeakerDisplayWindow: __init__ called")

        self.initial_speaker_name_font_size = 50
        self.initial_speaker_segment_font_size = 35
        self.initial_separator_font_size = 25
        self.initial_timer_font_size = 260
        self.initial_warning_font_size = 60

        self.initial_timer_fg = "#00FF99"
        self.initial_speaker_info_fg = "white"
        self.initial_warning_fg = "white" 

        self.title("Speaker Timer Display")
        self.geometry("1024x576")
        self.configure(bg="#0A0A0A")
        self.minsize(600, 300)

        self.normal_display_bg = "#0A0A0A"
        self.warning_blink_color = "#E74C3C"

        self.blink_job_id = None
        self._is_blinking = False

        self._resize_job_id = None
        self.RESIZE_DEBOUNCE_MS = 100

        self._create_widgets()
        self._center_window()

        self.bind("<Configure>", self._debounced_on_resize)
        self.update_idletasks()
        self._on_resize_final()

        self.attributes('-topmost', True)

    def _create_widgets(self):
        """
        Creates widgets for the speaker display using grid layout for precise control.
        """
        print("SpeakerDisplayWindow: _create_widgets called (using grid)")

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(4, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.speaker_name_label = tk.Label(self, text="SPEAKER NAME", font=("Inter", self.initial_speaker_name_font_size, "bold"),
                                           fg=self.initial_speaker_info_fg, bg=self.normal_display_bg, bd=0, relief="flat")
        self.speaker_name_label.grid(row=0, column=0, sticky="nsew", pady=(20, 0))

        self.separator_label = tk.Label(self, text="—", font=("Inter", self.initial_separator_font_size, "bold"),
                                        fg=self.initial_speaker_info_fg, bg=self.normal_display_bg, bd=0, relief="flat")
        self.separator_label.grid(row=1, column=0, sticky="nsew", pady=(0, 0))

        self.speaker_segment_label = tk.Label(self, text="SEGMENT / TOPIC", font=("Inter", self.initial_speaker_segment_font_size, "bold"),
                                              fg=self.initial_speaker_info_fg, bg=self.normal_display_bg, bd=0, relief="flat")
        self.speaker_segment_label.grid(row=2, column=0, sticky="nsew", pady=(0, 20))

        self.timer_label = tk.Label(self, text="00:00", font=("Inter", self.initial_timer_font_size, "bold"),
                                    fg=self.initial_timer_fg, bg=self.normal_display_bg, bd=0, relief="flat")
        self.timer_label.grid(row=3, column=0, sticky="nsew", pady=(10, 10))

        self.warning_message_label = tk.Label(self, text="", font=("Inter", self.initial_warning_font_size, "bold"),
                                              fg=self.initial_warning_fg, bg=self.normal_display_bg, bd=0, relief="flat")
        self.warning_message_label.grid(row=4, column=0, sticky="nsew", pady=(15, 20))

    def _debounced_on_resize(self, event):
        if self._resize_job_id:
            self.after_cancel(self._resize_job_id)
        self._resize_job_id = self.after(self.RESIZE_DEBOUNCE_MS, self._on_resize_final)

    def _on_resize_final(self):
        new_width = self.winfo_width()
        new_height = self.winfo_height()

        if new_width == 0 or new_height == 0:
            return

        overall_scale_factor = min(new_width / 1024.0, new_height / 576.0)

        min_timer_font_size = 90
        min_info_font_size = 16
        min_separator_font_size = 14
        min_warning_font_size = 22

        timer_font_size = max(min_timer_font_size, int(self.initial_timer_font_size * overall_scale_factor * 1.0))
        speaker_name_font_size = max(min_info_font_size, int(self.initial_speaker_name_font_size * overall_scale_factor * 0.9))
        speaker_segment_font_size = max(min_info_font_size, int(self.initial_speaker_segment_font_size * overall_scale_factor * 0.9))
        separator_font_size = max(min_separator_font_size, int(self.initial_separator_font_size * overall_scale_factor * 0.9))
        warning_font_size = max(min_warning_font_size, int(self.initial_warning_font_size * overall_scale_factor * 0.9))

        self.timer_label.config(font=("Inter", timer_font_size, "bold"))
        self.speaker_name_label.config(font=("Inter", speaker_name_font_size, "bold"))
        self.speaker_segment_label.config(font=("Inter", speaker_segment_font_size, "bold"))
        self.separator_label.config(font=("Inter", separator_font_size, "bold"))
        self.warning_message_label.config(font=("Inter", warning_font_size, "bold"))

    def _center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        print(f"SpeakerDisplayWindow: Centered at {x},{y} with size {width}x{height}")

    def _toggle_blink_color(self):
        if not self._is_blinking:
            if self.blink_job_id:
                self.after_cancel(self.blink_job_id)
                self.blink_job_id = None
            return

        current_bg = self.cget('bg')
        if current_bg == self.normal_display_bg:
            new_bg = self.warning_blink_color
        else:
            new_bg = self.normal_display_bg

        self.configure(bg=new_bg)
        self.timer_label.config(bg=new_bg)
        self.warning_message_label.config(bg=new_bg)
        self.speaker_name_label.config(bg=new_bg)
        self.speaker_segment_label.config(bg=new_bg)
        self.separator_label.config(bg=new_bg)

        self.blink_job_id = self.after(500, self._toggle_blink_color)

    def _start_blinking(self):
        if not self._is_blinking:
            self._is_blinking = True
            self.configure(bg=self.warning_blink_color)
            self.timer_label.config(bg=self.warning_blink_color)
            self.warning_message_label.config(bg=self.warning_blink_color)
            self.speaker_name_label.config(bg=self.warning_blink_color)
            self.speaker_segment_label.config(bg=self.warning_blink_color)
            self.separator_label.config(bg=self.warning_blink_color)
            self.blink_job_id = self.after(500, self._toggle_blink_color)

    def _stop_blinking(self):
        if self._is_blinking and self.blink_job_id:
            self.after_cancel(self.blink_job_id)
            self.blink_job_id = None
        self._is_blinking = False
        self.configure(bg=self.normal_display_bg)
        self.timer_label.config(bg=self.normal_display_bg)
        self.warning_message_label.config(bg=self.normal_display_bg)
        self.speaker_name_label.config(bg=self.normal_display_bg)
        self.speaker_segment_label.config(bg=self.normal_display_bg)
        self.separator_label.config(bg=self.normal_display_bg)

    def update_display(self, time_text, speaker_name, speaker_segment, is_warning, is_past_zero):
        self.timer_label.config(text=time_text)
        self.speaker_name_label.config(text=speaker_name.upper())
        self.speaker_segment_label.config(text=speaker_segment.upper())

        warning_fg_color = self.initial_warning_fg
        if is_warning or is_past_zero:
            warning_fg_color = "yellow"
        
        text_fg_color_other = "white" if is_warning or is_past_zero else self.initial_speaker_info_fg
        timer_fg_color = "white" if is_warning or is_past_zero else self.initial_timer_fg

        self.timer_label.config(fg=timer_fg_color)
        self.warning_message_label.config(fg=warning_fg_color)
        self.speaker_name_label.config(fg=text_fg_color_other)
        self.speaker_segment_label.config(fg=text_fg_color_other)
        self.separator_label.config(fg=text_fg_color_other)

        if is_past_zero:
            self._start_blinking()
            self.warning_message_label.config(text="TIME'S UP!")
        elif is_warning:
            self._start_blinking()
            self.warning_message_label.config(text="ROUND UP!")
        else:
            self._stop_blinking()
            self.warning_message_label.config(text="")


class ChurchTimerApp:
    def __init__(self, master):
        self.master = master
        master.title("Church Program Manager")
        master.geometry("1000x700")
        master.minsize(900, 650)
        master.configure(bg="#1E1E1E")

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TFrame', background="#282828")
        self.style.configure('TLabel', background="#282828", foreground="#D4D4D4", font=('Inter', 10))
        self.style.configure('TButton', font=('Inter', 12, 'bold'), borderwidth=0, relief="flat", foreground="white",
                             background="#3A3A3A", padding=[15, 10])
        self.style.map('TButton',
                       background=[('active', '#555555')],
                       foreground=[('disabled', '#888888')])
        self.style.configure('TEntry', fieldbackground="#3A3A3A", foreground="#D4D4D4", borderwidth=1, relief="flat")
        self.style.configure('TCombobox', fieldbackground="#3A3A3A", foreground="#D4D4D4", borderwidth=1, relief="flat")


        self.time_left = 0
        self.running = False
        self.warning_threshold = 60

        self.speakers = []
        self.current_speaker_index = -1

        self.speaker_display_window = None

        # --- HTTP Server Setup ---
        self.http_port = 8000 # Choose an unused port, 8000 is common for HTTP
        self.local_ip = self._get_local_ip()
        self.http_server_thread = HttpServerThread(self.local_ip, self.http_port)
        self.http_server_thread.daemon = True # Allow the thread to exit when main program exits
        self.http_server_thread.start()

        self._create_widgets()
        self._center_window()
        self._update_roster_display()
        self._load_speaker_details(-1)
        
        # Ensure server is stopped on app close
        self.master.protocol("WM_DELETE_WINDOW", self._on_app_close)


    def _get_local_ip(self):
        """Attempts to get the local IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1)) # Doesn't actually connect, just used to get the local IP
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1' # Fallback to localhost
        finally:
            s.close()
        return IP

    def _create_widgets(self):
        """
        Creates all the GUI widgets with an integrated and sophisticated layout.
        """
        # --- Main Layout (Grid) ---
        main_frame = ttk.Frame(self.master, padding="15", style='TFrame')
        main_frame.pack(fill="both", expand=True)

        main_frame.grid_columnconfigure(0, weight=2)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Timer Display and Controls ---
        left_panel = ttk.Frame(main_frame, style='TFrame', padding="20", relief="groove", borderwidth=2)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        self.current_speaker_label = tk.Label(left_panel, text="CURRENT SPEAKER: N/A", font=("Inter", 26, "bold"), fg="#D4D4D4", bg="#282828", wraplength=400)
        self.current_speaker_label.pack(pady=(10, 20), fill="x")

        self.timer_label = tk.Label(left_panel, text="00:00", font=("Inter", 100, "bold"), fg="#00FF7F", bg="#282828", bd=5, relief="flat")
        self.timer_label.pack(pady=20, fill="both", expand=True)

        self.warning_message_label = tk.Label(left_panel, text="", font=("Inter", 30, "bold"), fg="#FF4500", bg="#282828")
        self.warning_message_label.pack(pady=10)

        # Control Buttons Frame
        control_button_frame = ttk.Frame(left_panel, style='TFrame', padding="10 0 10 0")
        control_button_frame.pack(pady=20, fill="x")
        control_button_frame.grid_columnconfigure(0, weight=1)
        control_button_frame.grid_columnconfigure(1, weight=1)
        control_button_frame.grid_columnconfigure(2, weight=1)

        self.start_button = ttk.Button(control_button_frame, text="START", command=self._start_timer, style='TButton')
        self.start_button.grid(row=0, column=0, padx=5, pady=10, sticky="ew")
        self.style.configure('Start.TButton', background="#28a745", activebackground="#218838")
        self.start_button.config(style='Start.TButton')

        self.stop_button = ttk.Button(control_button_frame, text="STOP", command=self._stop_timer, style='TButton')
        self.stop_button.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        self.style.configure('Stop.TButton', background="#ffc107", activebackground="#e0a800", foreground="#333333")
        self.stop_button.config(style='Stop.TButton')

        self.reset_button = ttk.Button(control_button_frame, text="RESET", command=self._reset_timer, style='TButton')
        self.reset_button.grid(row=0, column=2, padx=5, pady=10, sticky="ew")
        self.style.configure('Reset.TButton', background="#007bff", activebackground="#0056b3")
        self.reset_button.config(style='Reset.TButton')

        self.next_speaker_button = ttk.Button(control_button_frame, text="NEXT SPEAKER", command=self._next_speaker, style='TButton')
        self.next_speaker_button.grid(row=1, column=0, columnspan=3, padx=5, pady=15, sticky="ew")
        self.style.configure('Next.TButton', background="#6f42c1", activebackground="#5a2f96")
        self.next_speaker_button.config(style='Next.TButton')

        # Button to open speaker display
        self.open_display_button = ttk.Button(control_button_frame, text="OPEN SPEAKER DISPLAY", command=self._open_speaker_display, style='TButton')
        self.open_display_button.grid(row=2, column=0, columnspan=3, padx=5, pady=10, sticky="ew")
        self.style.configure('Display.TButton', background="#17a2b8", activebackground="#138496")
        self.open_display_button.config(style='Display.TButton')

        # --- Mobile Sync (HTTP Server) Connection Info ---
        connection_info_frame = ttk.Frame(left_panel, style='TFrame', padding="10", relief="groove", borderwidth=1)
        connection_info_frame.pack(pady=10, fill="x")

        tk.Label(connection_info_frame, text="Mobile Sync (Local Network)", font=("Inter", 14, "bold"), fg="#D4D4D4", bg="#282828").pack(pady=(0, 5))
        
        self.ip_address_label = tk.Label(connection_info_frame, text=f"IP: {self.local_ip}", font=("Inter", 12), fg="#00FF99", bg="#282828")
        self.ip_address_label.pack(fill="x")
        
        self.port_label = tk.Label(connection_info_frame, text=f"Port: {self.http_port}", font=("Inter", 12), fg="#00FF99", bg="#282828")
        self.port_label.pack(fill="x")

        tk.Label(connection_info_frame, text="Enter this IP and Port into your mobile browser.", font=("Inter", 10), fg="#D4D4D4", bg="#282828", wraplength=250).pack(pady=(5,0))


        # --- Right Panel: Speaker Details, Roster, Messages ---
        right_panel = ttk.Frame(main_frame, style='TFrame', padding="15", relief="groove", borderwidth=2)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        right_panel.grid_rowconfigure(2, weight=1)
        right_panel.grid_rowconfigure(4, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)


        # Speaker Details Input Section
        speaker_details_frame = ttk.Frame(right_panel, style='TFrame', padding="10", relief="ridge", borderwidth=1)
        speaker_details_frame.pack(pady=(0, 15), fill="x")

        tk.Label(speaker_details_frame, text="Speaker Details", font=("Inter", 16, "bold"), fg="#D4D4D4", bg="#282828").pack(pady=(0, 10))

        tk.Label(speaker_details_frame, text="Name:", bg="#282828", fg="#D4D4D4", anchor="w").pack(fill="x")
        self.speaker_name_entry = ttk.Entry(speaker_details_frame, style='TEntry', font=('Inter', 12))
        self.speaker_name_entry.pack(fill="x", pady=(0, 5))

        tk.Label(speaker_details_frame, text="Title/Topic:", bg="#282828", fg="#D4D4D4", anchor="w").pack(fill="x")
        self.speaker_title_entry = ttk.Entry(speaker_details_frame, style='TEntry', font=('Inter', 12))
        self.speaker_title_entry.pack(fill="x", pady=(0, 5))

        tk.Label(speaker_details_frame, text="Time (MM:SS):", bg="#282828", fg="#D4D4D4", anchor="w").pack(fill="x")
        time_input_frame = ttk.Frame(speaker_details_frame, style='TFrame')
        time_input_frame.pack(fill="x", pady=(0, 5))
        time_input_frame.grid_columnconfigure(0, weight=1)
        time_input_frame.grid_columnconfigure(1, weight=1)
        self.minutes_entry = ttk.Entry(time_input_frame, style='TEntry', width=4, font=('Inter', 12), justify="center")
        self.minutes_entry.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.minutes_entry.insert(0, "05")
        tk.Label(time_input_frame, text=":", bg="#282828", fg="#D4D4D4").grid(row=0, column=1)
        self.seconds_entry = ttk.Entry(time_input_frame, style='TEntry', width=4, font=('Inter', 12), justify="center")
        self.seconds_entry.grid(row=0, column=2, sticky="ew", padx=(2, 0))
        self.seconds_entry.insert(0, "00")


        tk.Label(speaker_details_frame, text="Notes:", bg="#282828", fg="#D4D4D4", anchor="w").pack(fill="x")
        self.speaker_notes_text = tk.Text(speaker_details_frame, font=('Inter', 10), bg="#3A3A3A", fg="#D4D4D4",
                                          height=3, bd=1, relief="flat", wrap="word")
        self.speaker_notes_text.pack(fill="x", pady=(0, 10))

        self.add_update_speaker_button = ttk.Button(speaker_details_frame, text="ADD / UPDATE SPEAKER", command=self._add_update_speaker, style='TButton')
        self.add_update_speaker_button.pack(fill="x", pady=(0, 5))
        self.style.configure('AddUpdate.TButton', background="#1abc9c", activebackground="#16a085")
        self.add_update_speaker_button.config(style='AddUpdate.TButton')

        # Roster Management Section
        tk.Label(right_panel, text="Speaker Roster", font=("Inter", 16, "bold"), fg="#D4D4D4", bg="#282828").pack(pady=(10, 5))

        listbox_frame = tk.Frame(right_panel, bg="#333333", bd=1, relief="solid")
        listbox_frame.pack(padx=0, fill="both", expand=True)

        self.roster_listbox = tk.Listbox(listbox_frame, font=("Inter", 11), bg="#333333", fg="#D4D4D4",
                                          selectbackground="#007bff", selectforeground="white",
                                          height=10, relief="flat", bd=0, highlightthickness=0)
        self.roster_listbox.pack(side="left", fill="both", expand=True)
        self.roster_listbox.bind('<<ListboxSelect>>', self._on_roster_select)


        roster_scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.roster_listbox.yview)
        roster_scrollbar.pack(side="right", fill="y")
        self.roster_listbox.config(yscrollcommand=roster_scrollbar.set)

        roster_button_frame = ttk.Frame(right_panel, style='TFrame', padding="5 0")
        roster_button_frame.pack(pady=(5, 10), fill="x")
        roster_button_frame.grid_columnconfigure(0, weight=1)
        roster_button_frame.grid_columnconfigure(1, weight=1)


        self.remove_speaker_button = ttk.Button(roster_button_frame, text="REMOVE SELECTED", command=self._remove_speaker, style='TButton')
        self.remove_speaker_button.grid(row=0, column=0, padx=2, pady=5, sticky="ew")
        self.style.configure('Remove.TButton', background="#dc3545", activebackground="#c82333")
        self.remove_speaker_button.config(style='Remove.TButton')

        self.clear_fields_button = ttk.Button(roster_button_frame, text="CLEAR FIELDS", command=self._clear_speaker_input_fields, style='TButton')
        self.clear_fields_button.grid(row=0, column=1, padx=2, pady=5, sticky="ew")
        self.style.configure('Clear.TButton', background="#6c757d", activebackground="#5a6268")
        self.clear_fields_button.config(style='Clear.TButton')


        # Program Info / Messaging Section
        message_frame = ttk.Frame(right_panel, style='TFrame', padding="10", relief="ridge", borderwidth=1)
        message_frame.pack(pady=(10, 0), fill="both", expand=True)

        tk.Label(message_frame, text="CHECK TIME PLEASE", font=("Inter", 18, "bold"), fg="#FFC107", bg="#282828").pack(pady=(0, 10))

        tk.Label(message_frame, text="Program Notes / Messages:", bg="#282828", fg="#D4D4D4", anchor="w").pack(fill="x")
        self.program_notes_text = tk.Text(message_frame, font=('Inter', 10), bg="#3A3A3A", fg="#D4D4D4",
                                          height=4, bd=1, relief="flat", wrap="word")
        self.program_notes_text.pack(fill="both", expand=True, pady=(0, 5))
        self.program_notes_text.insert(tk.END, "Enter general program notes or messages here.")


        # Placeholder for other info like "Cue Finish", "Event Overdue"
        tk.Label(message_frame, text="Cue Finish: --:--", bg="#282828", fg="#999999", anchor="w").pack(fill="x")
        tk.Label(message_frame, text="Event Overdue: --:--", bg="#282828", fg="#999999", anchor="w").pack(fill="x")


    def _center_window(self):
        self.master.update_idletasks()
        width = self.master.winfo_width()
        height = self.master.winfo_height()
        x = (self.master.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master.winfo_screenheight() // 2) - (height // 2)
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def _open_speaker_display(self):
        print("ChurchTimerApp: _open_speaker_display called")
        if self.speaker_display_window is None or not self.speaker_display_window.winfo_exists():
            self.speaker_display_window = SpeakerDisplayWindow(self.master)
            self.speaker_display_window.protocol("WM_DELETE_WINDOW", self._on_speaker_display_close)
            print("ChurchTimerApp: SpeakerDisplayWindow created.")
            self._update_shared_timer_state() # Update shared state immediately
        else:
            self.speaker_display_window.lift()
            print("ChurchTimerApp: SpeakerDisplayWindow already exists, bringing to front.")

    def _on_speaker_display_close(self):
        print("ChurchTimerApp: _on_speaker_display_close called")
        if self.speaker_display_window:
            if self.speaker_display_window._resize_job_id:
                self.speaker_display_window.after_cancel(self.speaker_display_window._resize_job_id)
                self.speaker_display_window._resize_job_id = None
            self.speaker_display_window.destroy()
            self.speaker_display_window = None
            print("ChurchTimerApp: SpeakerDisplayWindow destroyed.")


    def _update_shared_timer_state(self):
        """Updates the globally shared timer_state dictionary."""
        speaker_name_to_display = "N/A"
        speaker_segment_to_display = "N/A"

        if self.current_speaker_index != -1 and self.speakers:
            current_speaker = self.speakers[self.current_speaker_index]
            speaker_name_to_display = current_speaker['name']
            speaker_segment_to_display = current_speaker['title']
        
        with timer_state_lock:
            timer_state["time_text"] = self.timer_label.cget("text")
            timer_state["speaker_name"] = speaker_name_to_display
            timer_state["speaker_segment"] = speaker_segment_to_display
            timer_state["is_warning"] = (0 < self.time_left <= self.warning_threshold)
            timer_state["is_past_zero"] = (self.time_left < 0)

        # Also update the local speaker display window if it's open
        if self.speaker_display_window and self.speaker_display_window.winfo_exists():
            self.speaker_display_window.update_display(
                timer_state["time_text"],
                timer_state["speaker_name"],
                timer_state["speaker_segment"],
                timer_state["is_warning"],
                timer_state["is_past_zero"]
            )


    def _update_timer(self):
        current_timer_bg = "#282828"
        current_timer_fg = "#00FF7F"
        current_warning_text = ""
        current_warning_bg = "#282828"
        current_warning_fg = "#FF4500"


        if self.running:
            self.time_left -= 1
            self._display_time()

            if self.time_left < 0:
                current_timer_bg = "#8B0000"
                current_timer_fg = "white"
                current_warning_text = "TIME'S UP!"
                current_warning_bg = "#8B0000"
                current_warning_fg = "white"
            elif 0 <= self.time_left <= self.warning_threshold:
                current_timer_bg = "#B22222"
                current_timer_fg = "white"
                current_warning_text = "ROUND UP!"
                current_warning_bg = "#B22222"
                current_warning_fg = "white"
            else:
                current_timer_bg = "#282828"
                current_timer_fg = "#00FF7F"
                current_warning_text = ""
                current_warning_bg = "#282828"
                current_warning_fg = "#FF4500"

            self.timer_label.config(bg=current_timer_bg, fg=current_timer_fg)
            self.warning_message_label.config(text=current_warning_text, bg=current_warning_bg, fg=current_warning_fg)

            self._update_shared_timer_state() # Update shared state and local display

            self.master.after(1000, self._update_timer)


    def _display_time(self):
        if self.time_left >= 0:
            minutes = self.time_left // 60
            seconds = self.time_left % 60
            time_format = f"{minutes:02d}:{seconds:02d}"
        else:
            abs_time_left = abs(self.time_left)
            minutes = abs_time_left // 60
            seconds = abs_time_left % 60
            time_format = f"-{minutes:02d}:{seconds:02d}"

        self.timer_label.config(text=time_format)

    def _start_timer(self):
        print("ChurchTimerApp: _start_timer called")
        if not self.running:
            if self.current_speaker_index == -1 and not self.speakers:
                messagebox.showerror("No Speaker", "Please add a speaker to the roster first, or select one using 'Next Speaker'.")
                return
            elif self.current_speaker_index == -1 and self.speakers:
                 self._load_speaker_details(0)

            if self.time_left == 0 and not self.speakers:
                messagebox.showerror("Invalid Time", "Please set a time for the speaker or load a speaker with allocated time.", parent=self.master)
                return
            elif self.time_left == 0 and self.current_speaker_index != -1 and self.speakers[self.current_speaker_index]['minutes'] == 0 and self.speakers[self.current_speaker_index]['seconds'] == 0:
                 messagebox.showerror("Invalid Time", "Current speaker has 00:00 time allocated. Please update their time.", parent=self.master)
                 return

            self.running = True
            self._update_timer()
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.reset_button.config(state="normal")
            print("ChurchTimerApp: Timer started.")

    def _stop_timer(self):
        print("ChurchTimerApp: _stop_timer called")
        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        print("ChurchTimerApp: Timer stopped.")

    def _reset_timer(self):
        print("ChurchTimerApp: _reset_timer called")
        self._stop_timer()
        if self.current_speaker_index != -1 and self.speakers and self.current_speaker_index < len(self.speakers):
            current_speaker = self.speakers[self.current_speaker_index]
            self.time_left = current_speaker['minutes'] * 60 + current_speaker['seconds']
            self._display_time()
            self.timer_label.config(bg="#282828", fg="#00FF7F")
            self.warning_message_label.config(text="", bg="#282828")
            self.current_speaker_label.config(text=f"CURRENT SPEAKER: {current_speaker['name'].upper()}")
        else:
            self.current_speaker_index = -1
            self.current_speaker_label.config(text="CURRENT SPEAKER: N/A")
            self.time_left = 0
            self._display_time()
            self.timer_label.config(bg="#282828", fg="#00FF7F")
            self.warning_message_label.config(text="", bg="#282828")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self._clear_speaker_input_fields()
            print("ChurchTimerApp: Timer reset.")
        
        self._update_shared_timer_state() # Send reset state to shared data


    def _add_update_speaker(self):
        print("ChurchTimerApp: _add_update_speaker called")
        speaker_name = self.speaker_name_entry.get().strip()
        speaker_title = self.speaker_title_entry.get().strip()
        speaker_notes = self.speaker_notes_text.get("1.0", tk.END).strip()
        minutes_str = self.minutes_entry.get().strip()
        seconds_str = self.seconds_entry.get().strip()

        if not speaker_name:
            messagebox.showerror("Input Error", "Speaker Name is required.", parent=self.master)
            return

        try:
            minutes = int(minutes_str)
            seconds = int(seconds_str)
            if not (0 <= minutes < 1000 and 0 <= seconds < 60):
                messagebox.showerror("Invalid Time", "Minutes must be 0-999 and Seconds 0-59.", parent=self.master)
                return
        except ValueError:
            messagebox.showerror("Invalid Time", "Please enter valid numbers for minutes and seconds.", parent=self.master)
            return

        selected_indices = self.roster_listbox.curselection()
        if selected_indices:
            index_to_update = selected_indices[0]
            self.speakers[index_to_update] = {
                'name': speaker_name,
                'title': speaker_title,
                'notes': speaker_notes,
                'minutes': minutes,
                'seconds': seconds
            }
            if self.current_speaker_index == index_to_update:
                self._load_speaker_details(index_to_update)
            messagebox.showinfo("Speaker Updated", f"'{speaker_name}' updated successfully.", parent=self.master)
            print(f"ChurchTimerApp: Speaker '{speaker_name}' updated at index {index_to_update}.")
        else:
            self.speakers.append({
                'name': speaker_name,
                'title': speaker_title,
                'notes': speaker_notes,
                'minutes': minutes,
                'seconds': seconds
            })
            messagebox.showinfo("Speaker Added", f"'{speaker_name}' added to roster.", parent=self.master)
            print(f"ChurchTimerApp: Speaker '{speaker_name}' added.")
            if self.current_speaker_index == -1:
                self._load_speaker_details(0)

        self._update_roster_display()
        self._clear_speaker_input_fields()


    def _remove_speaker(self):
        print("ChurchTimerApp: _remove_speaker called")
        try:
            selected_index = self.roster_listbox.curselection()[0]
            if messagebox.askyesno("Remove Speaker", f"Are you sure you want to remove '{self.speakers[selected_index]['name']}'?",
                                   parent=self.master):
                removed_name = self.speakers[selected_index]['name']
                del self.speakers[selected_index]
                self._update_roster_display()
                if self.current_speaker_index == selected_index:
                    self.current_speaker_index = -1
                    self._reset_timer()
                    self._clear_speaker_input_fields()
                    self.current_speaker_label.config(text="CURRENT SPEAKER: N/A")
                elif self.current_speaker_index > selected_index:
                    self.current_speaker_index -= 1
                print(f"ChurchTimerApp: Speaker '{removed_name}' removed.")
        except IndexError:
            messagebox.showwarning("No Selection", "Please select a speaker from the roster to remove.",
                                   parent=self.master)
            print("ChurchTimerApp: No speaker selected for removal.")

    def _on_roster_select(self, event):
        try:
            selected_index = self.roster_listbox.curselection()[0]
            speaker = self.speakers[selected_index]
            self.speaker_name_entry.delete(0, tk.END)
            self.speaker_name_entry.insert(0, speaker['name'])
            self.speaker_title_entry.delete(0, tk.END)
            self.speaker_title_entry.insert(0, speaker['title'])
            self.minutes_entry.delete(0, tk.END)
            self.minutes_entry.insert(0, f"{speaker['minutes']:02d}")
            self.seconds_entry.delete(0, tk.END)
            self.seconds_entry.insert(0, f"{speaker['seconds']:02d}")
            self.speaker_notes_text.delete("1.0", tk.END)
            self.speaker_notes_text.insert("1.0", speaker['notes'])

            if not self.running and self.current_speaker_index != selected_index:
                self._load_speaker_details(selected_index)
                self._update_roster_display()
                print(f"ChurchTimerApp: Speaker '{speaker['name']}' selected and loaded.")
        except IndexError:
            pass

    def _clear_speaker_input_fields(self):
        print("ChurchTimerApp: _clear_speaker_input_fields called")
        self.speaker_name_entry.delete(0, tk.END)
        self.speaker_title_entry.delete(0, tk.END)
        self.minutes_entry.delete(0, tk.END)
        self.minutes_entry.insert(0, "05")
        self.seconds_entry.delete(0, tk.END)
        self.seconds_entry.insert(0, "00")
        self.speaker_notes_text.delete("1.0", tk.END)


    def _update_roster_display(self):
        self.roster_listbox.delete(0, tk.END)
        for i, speaker in enumerate(self.speakers):
            time_str = f"{speaker['minutes']:02d}:{speaker['seconds']:02d}"
            display_text = f"{i+1}. {speaker['name']} ({time_str})"
            self.roster_listbox.insert(tk.END, display_text)
            if i == self.current_speaker_index:
                self.roster_listbox.itemconfig(i, {'bg': '#007bff', 'fg': 'white'})
            else:
                self.roster_listbox.itemconfig(i, {'bg': '#333333', 'fg': '#D4D4D4'})


    def _next_speaker(self):
        print("ChurchTimerApp: _next_speaker called")
        if not self.speakers:
            messagebox.showinfo("Roster Empty", "Please add speakers to the roster first.",
                               parent=self.master)
            return

        self._stop_timer()

        self.current_speaker_index += 1
        if self.current_speaker_index >= len(self.speakers):
            self.current_speaker_index = 0

        self._load_speaker_details(self.current_speaker_index)
        self._update_roster_display()
        print(f"ChurchTimerApp: Next speaker loaded. Index: {self.current_speaker_index}")

    def _load_speaker_details(self, index):
        print(f"ChurchTimerApp: _load_speaker_details called for index {index}")
        if 0 <= index < len(self.speakers):
            speaker = self.speakers[index]
            self.current_speaker_index = index
            self.time_left = speaker['minutes'] * 60 + speaker['seconds']
            self._display_time()
            self.current_speaker_label.config(text=f"CURRENT SPEAKER: {speaker['name'].upper()}")
            self.timer_label.config(bg="#282828", fg="#00FF7F")
            self.warning_message_label.config(text="", bg="#282828")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")

            # Update input fields to show current speaker's details
            self.speaker_name_entry.delete(0, tk.END)
            self.speaker_name_entry.insert(0, speaker['name'])
            self.speaker_title_entry.delete(0, tk.END)
            self.speaker_title_entry.insert(0, speaker['title'])
            self.minutes_entry.delete(0, tk.END)
            self.minutes_entry.insert(0, f"{speaker['minutes']:02d}")
            self.seconds_entry.delete(0, tk.END)
            self.seconds_entry.insert(0, f"{speaker['seconds']:02d}")
            self.speaker_notes_text.delete("1.0", tk.END)
            self.speaker_notes_text.insert("1.0", speaker['notes'])
            print(f"ChurchTimerApp: Details loaded for speaker: {speaker['name']}")

        else:
            self.current_speaker_index = -1
            self.current_speaker_label.config(text="CURRENT SPEAKER: N/A")
            self.time_left = 0
            self._display_time()
            self.timer_label.config(bg="#282828", fg="#00FF7F")
            self.warning_message_label.config(text="", bg="#282828")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self._clear_speaker_input_fields()
            print("ChurchTimerApp: No speaker loaded, resetting display to N/A.")

        self._update_shared_timer_state() # Update shared state after loading new speaker

    def _on_app_close(self):
        """Handles graceful shutdown of the HTTP server when the main app closes."""
        print("ChurchTimerApp: Main app closing. Stopping HTTP server...")
        if self.http_server_thread and self.http_server_thread.is_alive():
            self.http_server_thread.stop()
            self.http_server_thread.join(timeout=2) # Wait for the thread to finish
            if self.http_server_thread.is_alive():
                print("ChurchTimerApp: HTTP server thread did not terminate gracefully.")
        self.master.destroy()
        print("ChurchTimerApp: Main app destroyed.")


if __name__ == "__main__":
    root = tk.Tk()
    app = ChurchTimerApp(root)
    root.mainloop()










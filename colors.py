from colorama import init

# Цвет для прогресс-бара colour="#4462ca"
barcolor = "#4462ca"
bar_ansi = "\033[38;2;68;98;202m"
init(autoreset=True)

PINK = "\033[38;5;201m"
CYAN = "\033[38;2;0;255;255m"
GREEN = "\033[38;2;0;255;0m"
YELLOW = "\033[38;5;226m"
RED = "\033[38;2;255;0;0m"
BLUE = "\033[38;2;100;150;255m"
WHITE = "\033[38;2;255;255;255m"
UNDERLINE = "\033[4m"
ORANGE = "\033[38;2;255;165;0m"
CYAN_BG = "\033[46m"  # голубой фон
BROWN = "\033[38;2;181;101;29m"

RESET = "\033[0m"
ERASE = "\033[K"

x = f"{RED}❌{RESET}"
v = f"{GREEN}✔️{RESET}"
l = f"{RED}⛔{RESET}"
w = f"{ORANGE}▶️{RESET}"
o = f"{BLUE}🔍{RESET}"
t = f"{WHITE}⏳{RESET}"
d = f"{GREEN}💾{RESET}"
r = f"{CYAN}🔄{RESET}"
b = f"{PINK}🧠{RESET}"

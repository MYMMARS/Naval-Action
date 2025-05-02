import threading
import time
import requests
import json
import tkinter as tk
from tkinter import ttk, messagebox

# Constants (correct endpoints)
PORTS_URL = "https://storage.googleapis.com/nacleanopenworldprodshards/Ports_cleanopenworldprodeu2.json"
SHOPS_URL = "https://storage.googleapis.com/nacleanopenworldprodshards/Shops_cleanopenworldprodeu2.json"
ITEMS_URL = "https://storage.googleapis.com/nacleanopenworldprodshards/ItemTemplates_cleanopenworldprodeu2.json"
REFRESH_INTERVAL = 600000  # ms (10 minutes)
SAFE_PORTS = {
    "walkers cay", "turtle cay", "mangrove cay", "crown haven", "marsh harbor", "road rocks",
    "water bay", "west end", "little harbor", "la desconocida", "little isaac rocks", "morgans bluff",
    "williams bay", "mimbres", "nassau", "harbor island", "governors harbor", "arthurs town",
    "georges town", "deadmans cay", "watlings", "pitts town", "mayaguana"
}
INF = float('inf')

class AutocompleteCombobox(ttk.Combobox):
    """A Combobox with autocompletion that filters as you type, but only after 3 characters."""
    def set_completion_list(self, completion_list):
        self._completion_list = sorted(completion_list, key=str.lower)
        self['values'] = self._completion_list
        self.bind('<KeyRelease>', self._on_keyrelease)

    def _on_keyrelease(self, event):
        val = self.get().lower()
        if len(val) < 3:
            return
        data = [item for item in self._completion_list if val in item.lower()]
        self['values'] = data
        if data:
            self.event_generate('<Down>')  # open dropdown

class NavalActionGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Naval Action: Best Trade Prices by MYMMARS")
        self.geometry("1500x650")

        # Data caches
        self.ports = []
        self.shops = []
        self.items = []
        self.name_to_id = {}

        # Default tree config
        self.default_cols = ("id","name","buy_port","best_buy","buy_qty","sell_port",
                             "sell_price","sell_qty","profit_pct")
        self.default_headers = {
            "id":"Item ID","name":"Item Name","buy_port":"Buy From Port",
            "best_buy":"Buy Price","buy_qty":"Buy Qty","sell_port":"Sell To Port",
            "sell_price":"Sell Price","sell_qty":"Sell Qty","profit_pct":"% Profit"
        }

        # Controls frame
        ctrl = tk.Frame(self)
        ctrl.pack(fill="x", padx=5, pady=5)

        # Toggle for per-port item view
        self.per_port_view = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text="Per-Port Item View", variable=self.per_port_view,
                       command=self.process_data).pack(side="left", padx=5)

        # Item lookup combobox
        tk.Label(ctrl, text="Lookup Item:").pack(side="left", padx=(5,0))
        self.item_combo = AutocompleteCombobox(ctrl)
        self.item_combo.pack(side="left", padx=5)
        self.item_combo.bind('<<ComboboxSelected>>', lambda e: self.process_data())
        self.item_combo.bind('<KeyRelease>', lambda e: self.process_data())

        # Buy port selector
        tk.Label(ctrl, text="Buy From Port:").pack(side="left", padx=(10,0))
        self.buy_combo = AutocompleteCombobox(ctrl)
        self.buy_combo.pack(side="left", padx=5)
        self.buy_combo.bind('<<ComboboxSelected>>', lambda e: self.process_data())
        self.buy_combo.bind('<KeyRelease>', lambda e: self.process_data())

        # Sell port selector
        tk.Label(ctrl, text="Sell To Port:").pack(side="left", padx=(10,0))
        self.sell_combo = AutocompleteCombobox(ctrl)
        self.sell_combo.pack(side="left", padx=5)
        self.sell_combo.bind('<<ComboboxSelected>>', lambda e: self.process_data())
        self.sell_combo.bind('<KeyRelease>', lambda e: self.process_data())

        # Safe zone checkbox
        self.safe_only = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text="Safe Zone Only", variable=self.safe_only,
                       command=self.process_data).pack(side="left", padx=5)

        # Min buy qty
        tk.Label(ctrl, text="Min Buy Qty:").pack(side="left", padx=(10,0))
        self.min_buy_qty = tk.IntVar(value=0)
        tk.Spinbox(ctrl, from_=0, to=100000, textvariable=self.min_buy_qty,
                   width=6, command=self.process_data).pack(side="left", padx=5)

        # Min sell qty
        tk.Label(ctrl, text="Min Sell Qty:").pack(side="left", padx=(10,0))
        self.min_sell_qty = tk.IntVar(value=0)
        tk.Spinbox(ctrl, from_=0, to=100000, textvariable=self.min_sell_qty,
                   width=6, command=self.process_data).pack(side="left", padx=5)

        # Show negatives toggle
        self.show_negatives = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text="Show All (incl. negatives)",
                       variable=self.show_negatives,
                       command=self.process_data).pack(side="left", padx=5)

        # Treeview
        self.tree = ttk.Treeview(self, columns=self.default_cols, show="headings")
        self._configure_tree(self.default_cols, self.default_headers)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        # Fetch thread
        threading.Thread(target=self.fetch_data_thread, daemon=True).start()

    def _configure_tree(self, cols, headers):
        self.tree.config(columns=cols)
        for c in cols:
            self.tree.heading(c, text=headers.get(c, c),
                               command=lambda _c=c: self.sortby(_c, False))
            self.tree.column(c, width=120, anchor="center")
        # Ensure tags for coloring remain active after reconfiguration
        self.tree.tag_configure('good', foreground='green')
        self.tree.tag_configure('bad', foreground='red')

    def _fetch_json(self, url):
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        text = resp.text.strip()
        if text.startswith('var '):
            text = text.split('=',1)[1].rstrip(';')
        return json.loads(text)

    def fetch_data_thread(self):
        while True:
            try:
                self.ports = self._fetch_json(PORTS_URL)
                self.shops = self._fetch_json(SHOPS_URL)
                self.items = self._fetch_json(ITEMS_URL)
                port_names = [p.get('Name') or p.get('name') for p in self.ports]
                self.buy_combo.set_completion_list(port_names)
                self.sell_combo.set_completion_list(port_names)
                self.name_to_id = {itm.get('Name').lower(): itm.get('Id') for itm in self.items}
                self.item_combo.set_completion_list(list(self.name_to_id.keys()))
                self.after(0, self.process_data)
            except Exception as e:
                messagebox.showerror("Error fetching data", e)
            time.sleep(REFRESH_INTERVAL/1000)

    def process_data(self):
        if not (self.ports and self.shops and self.items):
            return
        if self.per_port_view.get():
            item_key = self.item_combo.get().lower()
            if item_key in self.name_to_id:
                self._display_item_across_ports(self.name_to_id[item_key])
                return
        self._display_best_trades()

    def _display_item_across_ports(self, item_id):
        cols = ("port","buy","bqty","sell","sqty","profit")
        headers = {"port":"Port","buy":"Buy Price","bqty":"Buy Qty",
                   "sell":"Sell Price","sqty":"Sell Qty","profit":"% Profit"}
        self._configure_tree(cols, headers)
        self.tree.delete(*self.tree.get_children())
        port_by_id = {str(p.get('Id')):(p.get('Name')).title() for p in self.ports}
        for shop in self.shops:
            pid = str(shop.get('Id'))
            port = port_by_id.get(pid,'Unknown')
            bid=bq=sp=sq=0
            for inv in shop.get('RegularItems',[]):
                if inv.get('TemplateId')==item_id:
                    bid=inv.get('BuyPrice',0); bq=inv.get('Quantity',0)
                    sp=inv.get('SellPrice',0); sq=inv.get('Quantity',0)
                    break
            if bid==0 and sp==0: continue
            pct = (sp-bid)/bid*100 if bid else 0
            tag = 'good' if pct>=0 else 'bad'
            self.tree.insert('', 'end', values=(port, f"{bid:.2f}", bq, f"{sp:.2f}", sq, f"{pct:+.2f}%"), tags=(tag,))

    def _display_best_trades(self):
        self._configure_tree(self.default_cols, self.default_headers)
        self.tree.delete(*self.tree.get_children())
        port_by_id = {str(p.get('Id')):(p.get('Name')).lower() for p in self.ports}
        name_by_id = {itm.get('Id'):(itm.get('Name')).lower() for itm in self.items}
        safe = self.safe_only.get(); min_sell=self.min_sell_qty.get(); min_buy=self.min_buy_qty.get(); show_all=self.show_negatives.get()
        buy_target=self.buy_combo.get().lower().strip(); sell_target=self.sell_combo.get().lower().strip()
        best={}
        for s in self.shops:
            port_l=port_by_id.get(str(s.get('Id')),'')
            if safe and port_l not in SAFE_PORTS: continue
            if buy_target and port_l!=buy_target: continue
            for inv in s.get('RegularItems',[]):
                iid=inv.get('TemplateId'); bp=inv.get('BuyPrice',INF); bq=inv.get('Quantity',0)
                if iid not in best or bp<best[iid]['buy'][0]: best[iid]={'buy':(bp,port_l),'buy_qty':bq,'sell':(-INF,None),'sell_qty':0}
        for s in self.shops:
            port_l=port_by_id.get(str(s.get('Id')),'')
            if safe and port_l not in SAFE_PORTS: continue
            if sell_target and port_l!=sell_target: continue
            for inv in s.get('RegularItems',[]):
                iid=inv.get('TemplateId'); sp=inv.get('SellPrice',-INF); sq=inv.get('Quantity',0)
                if iid in best and sp>best[iid]['sell'][0]: best[iid]['sell']=(sp,port_l); best[iid]['sell_qty']=sq
        rows=[]
        for iid,data in best.items():
            bp,bport=data['buy']; sp,sport=data['sell']; bq=data['buy_qty']; sq=data['sell_qty']
            if sp==-INF or bq<min_buy or sq<min_sell: continue
            pct=(sp-bp)/bp*100 if bp else 0
            if not show_all and pct<0: continue
            tag='good' if pct>=0 else 'bad'
            rows.append((pct,iid,name_by_id.get(iid),bport,bp,bq,sport,sp,sq,f"{pct:+.2f}%",tag))
        rows.sort(key=lambda x:x[0],reverse=True)
        for _,iid,name,bport,bp,bq,sport,sp,sq,pct_str,tag in rows:
            self.tree.insert('', 'end', values=(iid,name,bport,f"{bp:.2f}",bq,sport,f"{sp:.2f}",sq,pct_str), tags=(tag,))

    def sortby(self, col, desc):
        data=[(self.tree.set(k,col),k) for k in self.tree.get_children('')]
        def conv(v):
            try: return float(v.replace('%','')) if col in ('profit_pct','profit') else float(v)
            except: return v.lower()
        data=[(conv(v),k) for v,k in data]; data.sort(reverse=desc)
        for idx,(_,k) in enumerate(data): self.tree.move(k,'',idx)
        self.tree.heading(col, command=lambda: self.sortby(col, not desc))

if __name__=='__main__': NavalActionGUI().mainloop()
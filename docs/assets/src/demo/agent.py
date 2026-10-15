import json, httpx
B="http://localhost:18100"; H={"Accept":"application/json, text/event-stream","Authorization":"Bearer hermes-e2e"}
def tool(name, **a):
    r=httpx.post(B+"/mcp",headers=H,json={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":a}})
    line=[l for l in r.text.splitlines() if l.startswith("data: ")][0]
    return json.loads(json.loads(line[6:])["result"]["content"][0]["text"])
tool("get_message", mailbox="contato", uid="1")
tool("get_message", mailbox="contato", uid="2")
tool("send", mailbox="contato", to=["pedro@padariaalbuquerque.com.br"], subject="Re: Site novo da padaria",
     body_text="Combinado, Pedro! A versão 2 com a foto nova da vitrine sobe hoje à tarde.",
     in_reply_to="<demo1.contato@exemplo.com.br>")
tool("delete_message", mailbox="financeiro", uid="1")
tool("get_message", mailbox="contato", uid="3")
print("atividade do hermes criada")

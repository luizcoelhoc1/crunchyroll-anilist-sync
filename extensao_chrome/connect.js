(() => {
  if (location.pathname !== "/conectar" ||
      !document.querySelector('meta[name="cral-bridge"][content="1"]')) return;
  const key = location.hash.slice(1);
  if (!/^[a-f0-9]{64}$/.test(key)) return;
  const heading = document.getElementById("status");
  const details = document.getElementById("details");
  const services = document.getElementById("services");
  let ended = false;
  async function update(initial = false) {
    if (ended) return;
    try {
      const result = await chrome.runtime.sendMessage(initial ?
        {type: "cral-pair", origin: location.origin, key} : {type: "cral-status"});
      if (!result?.ok) throw new Error(result?.error || "Conexão indisponível.");
      services.textContent = "AniList: " + (result.received.al ? "recebido" : "aguardando") +
        " · Crunchyroll: " + (result.received.cr ? "recebido" : "aguardando");
      heading.textContent = result.complete ? "Acessos entregues ao programa!" : "Conectado ao Chrome. Aguardando os sites…";
      details.textContent = result.complete ?
        "Volte ao programa Python e clique em Gerar prévia. Você já pode fechar esta aba." :
        (result.error || "As abas de apoio foram abertas em segundo plano. Se algum site pedir login ou seleção de perfil, conclua nessa aba. Selecione no Crunchyroll o perfil cujo histórico deseja usar.");
      ended = Boolean(result.complete);
    } catch (error) {
      heading.textContent = "Não foi possível concluir a conexão.";
      details.textContent = error.message + " Volte ao programa e clique em Conectar pelo Chrome novamente.";
      ended = true;
    }
    if (!ended) setTimeout(update, 1500);
  }
  update(true);
})();

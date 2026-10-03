"use strict";
let language = "en";
try { if (localStorage.getItem("language") === "zh") language = "zh"; } catch { /* Optional storage. */ }
const languageListeners = [];
const tr = (en, zh) => language === "zh" ? zh : en;
function translatePage() {
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-en]").forEach((node) => {
    node.textContent = node.getAttribute(`data-${language}`);
  });
  document.querySelectorAll("[data-language]").forEach((node) => {
    node.hidden = node.getAttribute("data-language") !== language;
  });
  const search = document.querySelector("#search");
  if (search) search.placeholder = tr("Search title, author, journal or DOI", "搜索标题、作者、期刊或 DOI");
  const toggle = document.querySelector("#language-toggle");
  toggle.textContent = tr("中文", "English");
  toggle.setAttribute("aria-label", tr("Switch interface to Chinese", "切换界面为英文"));
  languageListeners.forEach((listener) => listener());
}
document.querySelector("#language-toggle").addEventListener("click", () => {
  language = language === "en" ? "zh" : "en";
  try { localStorage.setItem("language", language); } catch { /* Optional storage. */ }
  translatePage();
});
translatePage();

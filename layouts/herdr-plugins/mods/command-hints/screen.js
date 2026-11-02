// 从终端画面里识别正在输入的斜杠命令，以及 CLI 弹出的建议列表。
// 只解析 hc read 的纯文本输出，不向终端发送任何内容。

const INPUT_ROW = /^\s*[❯›]\s?(.*)$/;
const MENU_ROW = /^\s*(?:❯\s*)?(\/[A-Za-z0-9:_-]+)\s{2,}(\S.*?)\s*$/;
const SEPARATOR = /^\s*[─━═-]{8,}\s*$/;

export function parseSlashMenu(text) {
  const lines = String(text ?? '').split('\n').map((line) => line.replace(/\s+$/, ''));
  let input = null;
  let index = -1;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const match = lines[i].match(INPUT_ROW);
    if (match) {
      input = match[1].trim();
      index = i;
      break;
    }
  }
  if (!input || !input.startsWith('/')) return null;

  const typed = input.split(/\s+/)[0];
  const rows = [];
  for (let i = index - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (SEPARATOR.test(line)) {
      if (rows.length) break;
      continue;
    }
    const match = line.match(MENU_ROW);
    if (match) {
      if (!rows.some((row) => row.command === match[1])) {
        rows.unshift({ command: match[1], description: match[2].trim() });
      }
      continue;
    }
    if (rows.length) break;
  }
  return { typed, rows };
}

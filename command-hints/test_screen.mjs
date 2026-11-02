import assert from 'node:assert/strict';
import { parseSlashMenu } from './screen.js';

const MENU = `
  ❯ /model                      设置 Claude 的 AI 模型（当前 永不卡住 · routing group)
    /mobile                     显示二维码下载 Claude 移动应用
    /auto-mode-setup            让 auto mode 了解你的环境，并可选微调规则
────────────────────────────────────────────────────────────
❯ /mo
────────────────────────────────────────────────────────────
  ➜  Herdr git:(main) ✗
`;

assert.deepEqual(parseSlashMenu(MENU), {
  typed: '/mo',
  rows: [
    { command: '/model', description: '设置 Claude 的 AI 模型（当前 永不卡住 · routing group)' },
    { command: '/mobile', description: '显示二维码下载 Claude 移动应用' },
    { command: '/auto-mode-setup', description: '让 auto mode 了解你的环境，并可选微调规则' },
  ],
});

// 没有斜杠输入时不做任何处理
assert.equal(parseSlashMenu('  ❯ 修复这个问题\n  ➜  repo git:(main)\n'), null);

// 输入了斜杠但菜单还没弹出
assert.deepEqual(parseSlashMenu('  ➜  repo git:(main)\n❯ /zzz\n'), { typed: '/zzz', rows: [] });

// Codex 风格的提示符
assert.deepEqual(parseSlashMenu('  ❯ /review   Review the current diff\n──────\n› /re\n'), {
  typed: '/re', rows: [{ command: '/review', description: 'Review the current diff' }],
});

// 同一命令重复出现时只保留一次
assert.equal(parseSlashMenu('  ❯ /help  查看帮助\n    /help  查看帮助\n──────\n❯ /h\n').rows.length, 1);

console.log('command-hints: 解析测试通过');

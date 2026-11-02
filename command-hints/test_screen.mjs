import assert from 'node:assert/strict';
import { parseSlashMenu, findPhrases } from './screen.js';
import { PHRASES } from './phrases.js';

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

// Codex 使用 › 作为输入和选中标记
assert.deepEqual(parseSlashMenu('› /model        choose what model\n  /fast         1.5x speed\n──────\n› /\n'), {
  typed: '/', rows: [
    { command: '/model', description: 'choose what model' },
    { command: '/fast', description: '1.5x speed' },
  ],
});

// 英文文案对照
const codex = hcSample();
assert.deepEqual(findPhrases(codex, PHRASES).map((rule) => rule.en),
  ['? for shortcuts', 'weekly limit', 'resets at', '1 warning', 'f2 to view',
   'Ask Codex to do anything', 'Context 0% used']);
assert.deepEqual(findPhrases('  Tip: 使用 Ctrl+V 粘贴图片\n', PHRASES).map((rule) => rule.zh), ['提示：']);
assert.deepEqual(findPhrases('Yes\n  No\n', PHRASES).map((rule) => rule.zh), ['是', '否']);
assert.deepEqual(findPhrases('Yesterday the run failed\n', PHRASES), []);

function hcSample() {
  return [
    '  ⚠ weekly limit: 19% left · resets at 01:06 on 4 Nov · /status',
    '› Ask Codex to do anything',
    '  ~/Desktop/Herdr · GPT-6.1 Terra low · Context 0% used',
    '  ← for agents · ? for shortcuts',
    '  ⚠ 1 warning · f2 to view',
  ].join('\n');
}

console.log('command-hints: 解析测试通过');

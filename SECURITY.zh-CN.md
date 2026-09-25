# 安全与隐私

[English](SECURITY.md) · [中文](SECURITY.zh-CN.md)

这个项目处理**声纹** —— 生物识别数据 —— 以及产生它们的录音和转写。在多数隐私法域下，这属于敏感类别（PIPL 第 28 条、GDPR 第 9 条）。所以这里的隐私 bug，严重等级**高于**普通的功能 bug，而不是更低。

## 什么算这里的漏洞

- 任何真实录音、转写、姓名、邮箱地址或嵌入向量被提交进本仓库，或仍能通过历史取回
- 有代码路径把真实数据写进**被跟踪的**路径（`audio/`、`data.js`、`speakers.json`）却不警告用户
- 导出泄露了超出用户所要的内容 —— 比如格式里嵌进了绝对路径或主机名，或者在只选了单个录音时却导出了整个语料
- 任何让自带 demo 不再完全合成的东西
- 引入运行时网络访问的依赖或构建步骤

## 怎么上报

用 **[Security → Report a vulnerability](https://github.com/Icather/speaker-workbench/security/advisories/new)**（私有 advisory），**不要**开公开 issue —— 公开 issue 会把你正在上报的那次暴露再重复一遍。

如果这个问题**已经是公开的**（比如一个真实姓名正躺在 git 历史里），请明确说出来。这值得知道，而且它的修法是重写历史而不是发一个 PR —— 只有仓库所有者能做这件事。

请附上：路径或提交号、泄露了什么、以及现在是否还能取到（`git log` 能看见、和直接按 SHA 取回，是两个不同的答案 —— 为什么单靠 force-push 不够，见 GitHub 文档的 *Removing sensitive data*）。

## 这个项目承诺什么

- 自带的 demo 由 `tools/make_demo.py` 生成：虚构的人物、共振峰合成的语音、编造的转写。
- **每一个**对外资产 —— 示意图、截图、placeholder 文字、测试样本、示例姓名 —— 都出自那个生成器。没有任何一处是从真实语料里取的。
- 运行时不访问网络。浏览器界面不加载任何外部资源（favicon 是内联的 `data:` URI）。
- `audio/`、`data.js` 和 `speakers.json` **是被跟踪的**，因为 demo 随仓库一起提交。在把管线指向你自己的语料之前，先读 [CONTRIBUTING](CONTRIBUTING.zh-CN.md#拿自己的音频来开发) —— 那几个路径会被就地覆盖。

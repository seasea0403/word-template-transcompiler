# 检查与修复

## 统一机械检查

word_template.py check 调用 verify_docx.py，检查 OPC 路径、XML、内部关系、书签、内部超链接、REF/PAGEREF 目标和复杂域平衡。不访问外链，不证明视觉或语义。

expectations.json 可声明：

```json
{
  "exact_counts": {"tables": 2, "math": 3, "footnotes": 1},
  "minimum_counts": {"images": 1, "toc_fields": 1},
  "required_text": ["稿件中必须出现的独特句子"],
  "forbidden_text": ["本次确认应删的教学占位原文"],
  "preserve_parts": ["word/media/image1.png"],
  "sections": [{"pgSz": {"w": "11906"}, "pgMar": {"top": "1134"}}]
}
```

示例数值不是默认。计数支持 paragraphs、tables、math、display_math、images（引用数）、footnotes（非特殊脚注）、bookmarks、toc_fields、seq_fields、ref_fields。模板布局表计入 tables；预期应合并稿件和保留清单。preserve_parts 需要 --template 并按原始字节比对。sections 对每个 w:sectPr 按文档顺序比较声明属性，节数也要匹配。空预期不等于通过内容完整性检查。

## 需保留的回归经验

- 字号正确不等于字体正确：核验正文目标层级、脚本字体和网格，不能修改目录样式来修正文标题。
- 页设置逐节比较；说明与 sectPr 冲突要记录范围和裁决，不能把正文变化误报为全篇变化。
- 日期只填语义对应槽位，单月不能替代范围；文本框内外重复读取可能只是统计重复。
- 封面所有信息栏要一起比较，Tab 下划线和下划线空格的视觉结果不同；只检查端点不足。
- 三线表逐边框检查：缺属性不等于隐藏。线宽、表头加粗等按当前文字或示例取证。
- 目录链接有效仍可能缺摘要、自身、层级缩进或真实页码。收录集合、每级样例、字符/物理缩进、右 Tab、点线及页码字体分别核验。
- `{TC ...}` 是目录项域。查结构与隐藏属性，区分显示域代码/隐藏文字 UI 状态；更新提示本身不能证明有外部引用，先查实际关系和域。
- 大图继承正文 1.5 倍行距曾导致侵入页眉；修复图段行框后重分页，不靠移动页眉掩盖。
- 圈号脚注跨渲染器可能不同；Word 下的要求以 Word 设置和实际渲染验证。

## Word 更新和重开

Windows 有 Word 时：

```powershell
powershell -NoProfile -File <skill>/scripts/refresh_word.ps1 -Source <candidate.docx> -OutDir <fresh-check>
```

脚本在新副本关闭宏，更新正文、页眉页脚、注释的域及目录，重分页、保存、导出 PDF，关闭重开再重复。回执记录更新结果、目录缩进、页数和稳定性，无目录也支持。不遍历可能循环的 NextStoryRange；文本框等其他 story 的域仍需单独验证。默认 120 秒超时，仅清理脚本启动并记录的自动化 Word 进程，保留诊断。未成功返回错误，不以回执存在代替通过。

本次打包时的 Word COM 实测在 Documents.Open 阶段未完成，因此新版辅助脚本未取得成功刷新证据；已有三份历史成稿的更新证据不自动转移为这个新版脚本的运行证明。使用时以实际回执为准；结构、组件和契约测试已独立运行。

它不模拟用户插删章节或逐链接点击。需要编辑后更新时，在另一个副本做代表性编辑后验证；没有 Word 则明确此项未验证。不能把无 Word 的 LibreOffice 导出当 Word 更新证明。

用当前环境可用的 documents 配套渲染器，逐页检查最新输出的截断、重叠、字体、图表、页眉页脚和目录。渲染成功不自动写成视觉通过记录。

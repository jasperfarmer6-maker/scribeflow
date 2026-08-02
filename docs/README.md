# PDF 转 Markdown 文档中心

> 文档状态：以代码现状为准｜最后验证：2026-08-01｜项目版本：0.1.0｜应用版本：0.1.2

## 阅读顺序

1. [架构说明](architecture.md)
2. [转换流程](pipeline.md)
3. [模块边界](modules.md)
4. [模型说明](models.md)
5. [配置参考](configuration.md)
6. [能力边界](capabilities.md)
7. [已知问题](known-issues.md) 与 [性能瓶颈](performance.md)
8. [替换方案](replaceability.md)
9. [维护机制](maintenance.md)
10. [技术白皮书](whitepaper.md)

## 文档约定

- **已验证事实**：可以从代码、测试、构建产物或实际运行结果复核。
- **设计约束**：代码必须保持的安全、保真或兼容性规则。
- **已知推断**：基于当前依赖或上游行为的合理判断，不等于保证。
- **待验证项**：当前环境无法确认，必须在相应版本或机器上复测。

运行文档门禁：

```bash
.venv/bin/python scripts/check_docs.py
```

白皮书 PDF 由源文件生成：

```bash
.venv/bin/python scripts/build_whitepaper_pdf.py
```

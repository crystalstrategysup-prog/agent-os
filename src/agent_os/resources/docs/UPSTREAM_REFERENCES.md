# Источники интерфейсов и границы применения

Консультация: 2026-09-25. Документация — не доказательство конкретного Mac runtime.

- OpenAI, AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
  Global AGENTS.override.md имеет приоритет перед AGENTS.md; проектные инструкции
  уточняют цепочку до cwd. После изменения нужен новый запуск/сеанс для чтения цепочки.
- OpenAI, hooks: https://learn.chatgpt.com/docs/hooks
  Stop decision=block может продолжить turn; stop_hook_active сообщает повторный проход.
  Это объясняет историческую ошибку beta.4, а не разрешает использовать hooks в beta.5.

Текущий контракт: никаких native hooks/самодоверия/восстановления из backups. AGENTS/skills
не техническая песочница; правила клиента и target executor остаются отдельными контролями.
Изменение возможностей клиента требует новой явной проверки, не тихого расширения authority.

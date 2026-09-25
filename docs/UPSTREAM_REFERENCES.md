# Проверенные источники интерфейсов

Дата консультации: 2026-09-25. Это источники форматов, не гарантия поддержки на конкретном Mac.

- OpenAI, AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
  Инструкции читаются при запуске; global override имеет приоритет, ближайший проектный файл
  уточняет; объём инструкций ограничен. Поэтому install не создаёт новый global override поверх старого.
- OpenAI, Skills: https://learn.chatgpt.com/docs/build-skills
  SKILL.md c name/description; repo .agents/skills и user ~/.agents/skills. Навык сам по себе
  не является техническим принуждением; для действия нужны trusted hooks и пробы.
- OpenAI, Hooks: https://learn.chatgpt.com/docs/hooks
  SessionStart/UserPromptSubmit/PreToolUse/Stop, hookSpecificOutput, permissionDecision,
  native review/trust; не все виды tooling покрыты. Не self-trust и не permissive fallback.
- SemVer: https://semver.org/ — prerelease beta не выдаётся за стабильный выпуск.

Точные API/флаги необходимо сверить с установленным клиентом при передаче: документация
может обновляться отдельно от приложения. При несовместимости coordinator фиксирует BLOCKED
и исправляет adapter в отдельном документированном stage, не отключает gate для «успешной установки».

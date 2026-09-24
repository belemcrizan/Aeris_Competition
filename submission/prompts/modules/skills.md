# Skills

Helper scripts are packaged as skills. Run a script with run_skill_script, giving the skill name, the script file name and its arguments exactly as documented below; read a skill's SKILL.md with load_skill when you need details. Scripts run in the same container as run_command, cost budget like any command, print compact plain text, and write their state only under /tmp, never into /workspace. If a script reports an error, read the message and continue with ordinary commands rather than retrying it unchanged.

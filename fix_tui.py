import re

with open("tui.py", "r") as f:
    content = f.read()

# Remove the StrategiesTab class completely
# It starts at `class StrategiesTab(Container):` and goes up to `class QueuePanel(Container):`
content = re.sub(r'class StrategiesTab\(Container\):.*?class QueuePanel\(Container\):', 'class QueuePanel(Container):', content, flags=re.DOTALL)

# Remove the TabPane entry
content = re.sub(r'\s*with TabPane\("STRATEGIES"\): yield StrategiesTab\(\)\n', '\n', content)

# Remove import if any
content = re.sub(r'from app\.core\.strategy_manager import StrategyManager\n?', '', content)

with open("tui.py", "w") as f:
    f.write(content)

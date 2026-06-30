from abc import ABC, abstractmethod


class BaseSkill(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_schema(self) -> dict:
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get_all_schemas(self) -> list[dict]:
        return [skill.get_schema() for skill in self._skills.values()]

    def execute(self, name: str, kwargs: dict) -> str:
        if name not in self._skills:
            return f"技能执行失败：未知的技能名【{name}】。"

        try:
            return self._skills[name].execute(**kwargs)
        except Exception as e:
            return f"技能执行出错：{str(e)}"

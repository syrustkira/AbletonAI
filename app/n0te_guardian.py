from enum import Enum
from dataclasses import dataclass
class Priority(str,Enum):REALTIME="REALTIME";INTERACTIVE="INTERACTIVE";BACKGROUND="BACKGROUND";BULK="BULK"
class GuardianProfile(str,Enum):AUTO="AUTO";STUDIO_MAXIMUM="STUDIO_MAXIMUM";BALANCED="BALANCED";TRAVEL_BATTERY="TRAVEL_BATTERY";BACKGROUND="BACKGROUND"
@dataclass(frozen=True)
class WorkItem:name:str;priority:Priority;category:str
class WorkScheduler:
 def __init__(self,profile=GuardianProfile.AUTO):self.profile=profile;self.sensitive=False
 def set_sensitive(self,value:bool):self.sensitive=bool(value)
 def decision(self,item:WorkItem):
  if item.priority is Priority.REALTIME:return "RUN"
  if self.sensitive and (item.priority in {Priority.BACKGROUND,Priority.BULK} or item.category in {"ai_churn","indexing","pruning","sync","render","heavy_analysis"}):return "DEFER"
  if self.profile is GuardianProfile.STUDIO_MAXIMUM and item.priority is Priority.BULK:return "DEFER"
  if self.profile is GuardianProfile.TRAVEL_BATTERY and item.priority in {Priority.BACKGROUND,Priority.BULK}:return "THROTTLE"
  if self.profile is GuardianProfile.BACKGROUND and item.priority is Priority.INTERACTIVE:return "THROTTLE"
  return "RUN"

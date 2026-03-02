from __future__ import annotations

from dataclasses import dataclass

from ..auth_settings import RegistrationSettings, RegistrationSettingsStore


@dataclass
class AuthSettingsService:
    registration_store: RegistrationSettingsStore

    def load_registration(self) -> RegistrationSettings:
        return self.registration_store.load()

    def save_registration(self, enabled: bool) -> RegistrationSettings:
        return self.registration_store.save(RegistrationSettings(enabled=bool(enabled)))

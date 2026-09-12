#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import secrets
import hashlib
import hmac
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

try:
    _
except NameError:
    import gettext
    _ = gettext.gettext

class AuthManager:
    """Parolayı PBKDF2-HMAC-SHA256 ve rastgele kriptografik tuz (salt) ile
    güvenli şekilde hashleyip ~/.config/thisismytube/auth.json içinde saklar."""

    def __init__(self, config_dir=None):
        self.config_dir = config_dir or os.path.expanduser('~/.config/thisismytube')
        self.auth_file = os.path.join(self.config_dir, "auth.json")

    def is_password_set(self):
        if not os.path.exists(self.auth_file):
            return False
        try:
            with open(self.auth_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return bool(data.get("hash") and data.get("salt"))
        except Exception:
            return False

    def set_password(self, raw_password):
        os.makedirs(self.config_dir, exist_ok=True)
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            raw_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        data = {
            "salt": salt,
            "hash": key.hex()
        }
        with open(self.auth_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def verify_password(self, raw_password):
        if not self.is_password_set():
            return False
        try:
            with open(self.auth_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            salt = data.get("salt", "")
            stored_hash = data.get("hash", "")
            test_key = hashlib.pbkdf2_hmac(
                'sha256',
                raw_password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hmac.compare_digest(test_key.hex(), stored_hash)
        except Exception:
            return False

    def remove_password(self):
        if os.path.exists(self.auth_file):
            try:
                os.remove(self.auth_file)
            except Exception:
                pass


class VerifyPasswordDialog(QDialog):
    """Private moda geçerken açılan parola sorgulama penceresi."""

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.setWindowTitle(_("Güvenlik Doğrulaması"))
        self.setFixedSize(340, 160)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        info_label = QLabel(_("Private Mod için parolayı giriniz:"))
        info_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(info_label)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText(_("Parola"))
        self.pwd_input.setFixedHeight(34)
        self.pwd_input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self.pwd_input)

        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton(_("İptal"))
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton(_("Giriş Yap"))
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._on_confirm)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        self.pwd_input.setFocus()

    def _on_confirm(self):
        password = self.pwd_input.text()
        if self.auth_manager.verify_password(password):
            self.accept()
        else:
            QMessageBox.critical(self, _("Hata"), _("Hatalı parola! Erişim engellendi."))
            self.pwd_input.clear()
            self.pwd_input.setFocus()


class SetPasswordDialog(QDialog):
    """İndeksleme ekranından parola belirleme / değiştirme / kaldırma penceresi."""

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.is_existing = self.auth_manager.is_password_set()

        self.setWindowTitle(_("Private Mod Parolası Belirle"))
        self.setFixedWidth(360)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel(_("Private Mod Güvenlik Ayarı"))
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        if self.is_existing:
            layout.addWidget(QLabel(_("Mevcut Parola:")))
            self.old_pwd = QLineEdit()
            self.old_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.old_pwd.setFixedHeight(32)
            layout.addWidget(self.old_pwd)

        layout.addWidget(QLabel(_("Yeni Parola:")))
        self.new_pwd = QLineEdit()
        self.new_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pwd.setFixedHeight(32)
        layout.addWidget(self.new_pwd)

        layout.addWidget(QLabel(_("Yeni Parola (Tekrar):")))
        self.confirm_pwd = QLineEdit()
        self.confirm_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pwd.setFixedHeight(32)
        layout.addWidget(self.confirm_pwd)

        btn_row = QHBoxLayout()
        if self.is_existing:
            self.remove_btn = QPushButton(_("Parolayı Kaldır"))
            self.remove_btn.setStyleSheet("color: #cc3333;")
            self.remove_btn.clicked.connect(self._on_remove)
            btn_row.addWidget(self.remove_btn)

        btn_row.addStretch(1)

        cancel_btn = QPushButton(_("İptal"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton(_("Kaydet"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self):
        if self.is_existing:
            if not self.auth_manager.verify_password(self.old_pwd.text()):
                QMessageBox.critical(self, _("Hata"), _("Mevcut parolanızı yanlış girdiniz!"))
                return

        new_p = self.new_pwd.text()
        conf_p = self.confirm_pwd.text()

        if not new_p:
            QMessageBox.warning(self, _("Uyarı"), _("Parola boş bırakılamaz."))
            return

        if new_p != conf_p:
            QMessageBox.warning(self, _("Uyarı"), _("Girdiğiniz yeni parolalar birbiriyle eşleşmiyor!"))
            return

        self.auth_manager.set_password(new_p)
        QMessageBox.information(self, _("Başarılı"), _("Private mod parolası başarıyla kaydedildi."))
        self.accept()

    def _on_remove(self):
        if not self.auth_manager.verify_password(self.old_pwd.text()):
            QMessageBox.critical(self, _("Hata"), _("Parolayı kaldırmak için mevcut parolayı doğru girmelisiniz."))
            return

        confirm = QMessageBox.question(
            self, _("Onay"), _("Private mod parolasını tamamen kaldırmak istediğinize emin misiniz?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.auth_manager.remove_password()
            QMessageBox.information(self, _("Başarılı"), _("Parola koruması kaldırıldı."))
            self.accept()
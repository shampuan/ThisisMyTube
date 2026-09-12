#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QScrollArea, QMessageBox, QFileDialog, QComboBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

# gettext için yedek tanımlama (thisismytube.py install etmezse çökmesin diye)
try:
    _
except NameError:
    import gettext
    _ = gettext.gettext


class SettingRow(QFrame):
    """
    Kompakt Ayar Satırı: Solda başlık ve açıklama, sağda eylem butonu.
    """
    def __init__(self, title: str, description: str, button_text: str, button_callback, is_danger: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "SettingRow { "
            "   background-color: palette(base); "
            "   border: 1px solid palette(mid); "
            "   border-radius: 6px; "
            "} "
            "QLabel { border: none; background: transparent; }"
        )

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(16)

        # Sol taraf: Başlık ve Açıklama
        text_container = QVBoxLayout()
        text_container.setContentsMargins(0, 0, 0, 0)
        text_container.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        text_container.addWidget(title_lbl)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        # Her temada (açık/koyu) yüzde 100 net okunur, hafif küçük punto
        desc_lbl.setStyleSheet("color: palette(text); font-size: 9pt; opacity: 0.85;")
        text_container.addWidget(desc_lbl)

        row_layout.addLayout(text_container, 1)

        # Sağ taraf: Eylem Butonu
        self.button = QPushButton(button_text)
        self.button.setFixedHeight(32)
        self.button.setMinimumWidth(120)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)

        if is_danger:
            self.button.setStyleSheet(
                "QPushButton { "
                "   background-color: #d9534f; color: #ffffff; "
                "   border: 1px solid #c9302c; border-radius: 4px; "
                "   font-weight: bold; padding: 4px 12px; "
                "} "
                "QPushButton:hover { background-color: #c9302c; }"
            )
        else:
            self.button.setStyleSheet(
                "QPushButton { "
                "   background-color: palette(button); color: palette(button-text); "
                "   border: 1px solid palette(mid); border-radius: 4px; "
                "   padding: 4px 12px; font-weight: 500; "
                "} "
                "QPushButton:hover { "
                "   background-color: palette(highlight); color: palette(highlighted-text); "
                "}"
            )

        self.button.clicked.connect(button_callback)
        row_layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignVCenter)

class SettingComboRow(QFrame):
    """
    Sağında açılır kutu (QComboBox) bulunan ayar satırı (Örn: Dil seçimi).
    """
    def __init__(self, title: str, description: str, items: list, on_change_callback, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "SettingComboRow { "
            "   background-color: palette(base); "
            "   border: 1px solid palette(mid); "
            "   border-radius: 6px; "
            "} "
            "QLabel { border: none; background: transparent; }"
        )

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(16)

        text_container = QVBoxLayout()
        text_container.setContentsMargins(0, 0, 0, 0)
        text_container.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        text_container.addWidget(title_lbl)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: palette(text); font-size: 9pt; opacity: 0.85;")
        text_container.addWidget(desc_lbl)

        row_layout.addLayout(text_container, 1)

        self.combo = QComboBox()
        self.combo.setFixedHeight(32)
        self.combo.setMinimumWidth(140)
        for label, data in items:
            self.combo.addItem(label, data)

        self.combo.currentIndexChanged.connect(lambda idx: on_change_callback(self.combo.itemData(idx)))
        row_layout.addWidget(self.combo, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_active_code(self, code: str):
        self.combo.blockSignals(True)
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == code:
                self.combo.setCurrentIndex(i)
                break
        self.combo.blockSignals(False)

class SettingsView(QWidget):
    backup_requested = pyqtSignal(str)
    restore_requested = pyqtSignal(str)
    reset_requested = pyqtSignal()
    clear_cache_requested = pyqtSignal()
    language_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(10)

        # Sayfa Başlığı
        title_label = QLabel(_("Uygulama Ayarları"))
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setContentsMargins(0, 0, 0, 6)
        layout.addWidget(title_label)

        # --- Ayar Satırları ---

        # 0. Dil Seçimi
        self.row_lang = SettingComboRow(
            title=_("Uygulama Dili"),
            description=_("Arayüzün görüntüleneceği dili seçin. (Değişikliğin geçerli olması için yeniden başlatma gerekir)"),
            items=[("Türkçe", "tr"), ("English", "en")],
            on_change_callback=self._on_lang_selected
        )
        layout.addWidget(self.row_lang)

        # 1. Yedekleme
        row_backup = SettingRow(
            title=_("Ayarları ve İndeksi Yedekle"),
            description=_("Taranan klasörleri, video listesini, yıldız puanlarını ve notlarınızı tek bir dosyaya kaydeder."),
            button_text=_("Yedek Al..."),
            button_callback=self._on_backup_clicked
        )
        layout.addWidget(row_backup)

        # 2. Geri Yükleme
        row_restore = SettingRow(
            title=_("Yedekten Geri Yükle"),
            description=_("Daha önce alınmış bir yedek dosyasını geri yükleyerek arşivinizi ve ayarlarınızı tazeler."),
            button_text=_("Geri Yükle..."),
            button_callback=self._on_restore_clicked
        )
        layout.addWidget(row_restore)

        # 3. Önbellek Temizleme
        row_cache = SettingRow(
            title=_("Küçük Resim (Thumbnail) Önbelleğini Temizle"),
            description=_("Otomatik oluşturulan tüm video kapak resimlerini silerek diskte yer açar. Gerektiğinde tekrar üretilirler."),
            button_text=_("Önbelleği Boşalt"),
            button_callback=self._on_clear_cache_clicked
        )
        layout.addWidget(row_cache)

        # 4. Sıfırlama
        row_reset = SettingRow(
            title=_("Fabrika Ayarlarına Sıfırla"),
            description=_("Tüm taranmış videoları, puanları, kişisel notları ve dizin tanımlarını tamamen siler."),
            button_text=_("Her Şeyi Sıfırla"),
            button_callback=self._on_reset_clicked,
            is_danger=True
        )
        layout.addWidget(row_reset)

        layout.addStretch(1)
        scroll_area.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

    def set_current_language(self, lang_code: str):
        if hasattr(self, 'row_lang'):
            self.row_lang.set_active_code(lang_code)

    def _on_lang_selected(self, lang_code: str):
        self.language_changed.emit(lang_code)

    def _on_backup_clicked(self):
        file_path, _filter = QFileDialog.getSaveFileName(
            self, _("Yedek Dosyası Kaydet"), "thisismytube_backup.json", _("JSON Dosyaları (*.json)")
        )
        if file_path:
            self.backup_requested.emit(file_path)

    def _on_restore_clicked(self):
        file_path, _filter = QFileDialog.getOpenFileName(
            self, _("Yedek Dosyası Seçin"), "", _("JSON Dosyaları (*.json)")
        )
        if file_path:
            confirm = QMessageBox.question(
                self, _("Geri Yükleme Onayı"), 
                _("Mevcut ayarlarınız ve video indeksiniz bu yedekle değiştirilecek. Onaylıyor musunuz?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.restore_requested.emit(file_path)

    def _on_clear_cache_clicked(self):
        confirm = QMessageBox.question(
            self, _("Önbellek Temizleme"), 
            _("Oluşturulmuş tüm video küçük resimleri silinecektir. Onaylıyor musunuz?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.clear_cache_requested.emit()

    def _on_reset_clicked(self):
        confirm = QMessageBox.warning(
            self, _("Dikkat: Sıfırlama"), 
            _("Tüm kayıtlı videolar, notlar, puanlamalar ve dizinler kalıcı olarak silinecek!\n\nBu işlem geri alınamaz. Devam edilsin mi?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.reset_requested.emit()
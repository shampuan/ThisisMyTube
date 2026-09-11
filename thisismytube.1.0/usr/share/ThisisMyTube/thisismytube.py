#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
# Wayland/GNOME uyumluluğu: Önce xcb (MPV video gömme kararlılığı için), yoksa wayland dene
os.environ.setdefault("QT_QPA_PLATFORM", "xcb;wayland")

# --- YEREL AYAR DÜZELTMESİ (Non-C locale detected sorununu gidermek için) ---
os.environ['LC_NUMERIC'] = 'C'
import locale
try:
    locale.setlocale(locale.LC_ALL, 'C')
except locale.Error:
    try:
        locale.setlocale(locale.LC_NUMERIC, 'C')
    except locale.Error:
        pass
# -----------------------------------------------------------------------------    
import sys
# Programın bulunduğu dizini daima ilk arama sırasına al (Taşınabilirlik garantisi)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import random
import hashlib
import subprocess
import json
import gettext
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy, QSlider,
    QScrollArea, QGridLayout, QStackedWidget, QMessageBox,
    QTextEdit, QFileDialog, QStyle, QStyleOption, QRadioButton, QButtonGroup,
    QComboBox, QProgressBar, QListWidget, QListWidgetItem, QGraphicsDropShadowEffect, QCheckBox
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QMouseEvent, QPainter, QDesktopServices, QColor
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QPoint, QRunnable, QThreadPool, QObject, QTimer, QUrl

# --- ÇOK DİLLİ DESTEK (gettext / i18n) ---
def setup_i18n():
    config_dir = os.path.expanduser('~/.config/thisismytube')
    settings_file = os.path.join(config_dir, "settings.json")
    lang = "en"
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                lang = cfg.get("language", "en")
        except Exception:
            pass

    locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
    try:
        translation = gettext.translation("thisismytube", localedir=locales_dir, languages=[lang], fallback=True)
        translation.install()
        return translation.gettext
    except Exception:
        return gettext.gettext

_ = setup_i18n()
# ------------------------------------------

from settings_view import SettingsView
from private_auth import AuthManager, SetPasswordDialog, VerifyPasswordDialog

# MPV Entegrasyonu İçin Gerekli Kütüphane
try:
    import mpv
except ImportError:
    print("HATA: 'python-mpv' kütüphanesi bulunamadı. Lütfen 'pip install python-mpv' ile kurunuz.")
    sys.exit(1)



class ThumbSignals(QObject):
    finished = pyqtSignal(str, str) # video_path, thumb_path

class ThumbnailWorker(QRunnable):
    def __init__(self, video_path, thumb_path):
        super().__init__()
        self.video_path = video_path
        self.thumb_path = thumb_path
        self.signals = ThumbSignals()

    def run(self):
        if not os.path.exists(self.thumb_path):
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", "00:00:05",
                    "-i", self.video_path,
                    "-vframes", "1",
                    "-vf", "scale=320:-1",
                    "-q:v", "4",
                    self.thumb_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            except Exception:
                pass
        if os.path.exists(self.thumb_path):
            self.signals.finished.emit(self.video_path, self.thumb_path)





class ClickableLabel(QLabel):
    """Sol tıklamayla 'clicked' sinyali yayan, fare üzerine gelince parlayan
    bir QLabel — logoyu tıklanabilir ve 'canlı' hissettirmek için kullanılıyor."""
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setColor(QColor(255, 255, 255, 230))
        self._glow.setOffset(0, 0)
        self._glow.setBlurRadius(25)
        self._glow.setEnabled(False)  # Başlangıçta pasif
        self.setGraphicsEffect(self._glow)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._glow.setEnabled(True)
        self.update()
        if self.parentWidget():
            self.parentWidget().update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._glow.setEnabled(False)
        self.update()
        if self.parentWidget():
            self.parentWidget().update()
        super().leaveEvent(event)

class StarRatingWidget(QWidget):
    """7 yıldıza kadar tıklanabilir, basit bir puanlama widget'ı. Zaten
    seçili olan yıldıza tekrar tıklarsan puan sıfırlanır (temizleme kolaylığı)."""
    rating_changed = pyqtSignal(int)

    def __init__(self, max_stars=7, parent=None):
        super().__init__(parent)
        self.max_stars = max_stars
        self._rating = 0
        self._star_labels = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for i in range(self.max_stars):
            lbl = ClickableLabel("\u2606")
            lbl.setFont(QFont("Arial", 14))
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.clicked.connect(lambda checked=False, idx=i: self._on_star_clicked(idx))
            layout.addWidget(lbl)
            self._star_labels.append(lbl)

    def set_rating(self, value):
        self.blockSignals(True)
        self._rating = max(0, min(self.max_stars, value or 0))
        self._refresh()
        self.blockSignals(False)

    def rating(self):
        return self._rating

    def _on_star_clicked(self, idx):
        clicked_value = idx + 1
        self._rating = 0 if clicked_value == self._rating else clicked_value
        self._refresh()
        self.rating_changed.emit(self._rating)

    def _refresh(self):
        for i, lbl in enumerate(self._star_labels):
            # Boş/dolu ayrımı karakterle değil sadece renkle yapılıyor —
            # "☆" (boş yıldız) karakteri zaten çok ince/soluk olduğu için
            # bazı temalarda arka planla neredeyse görünmez oluyordu.
            lbl.setText("\u2605")
            lbl.setStyleSheet("color: #f5b301;" if i < self._rating else "color: #888888;")



class CollapsibleModeMenu(QWidget):
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation_duration = 200
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.toggle_button = QPushButton(_("\u25bc Mod Seçeneği"))
        self.toggle_button.clicked.connect(self.toggle)
        self.main_layout.addWidget(self.toggle_button)

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 5, 10, 5)
        content_layout.setSpacing(6)

        # Radyo butonları ile mod seçimi (Etiketler çevrilir, key'ler sabit kalır)
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        self.button_group = QButtonGroup(self)
        self.mode_buttons = {}
        mode_items = [
            (_("Normal Mod"), "Normal"),
            (_("Private Mod"), "Adult"),
            (_("Dizi Mod"), "Dizi"),
            (_("Sinema Mod"), "Sinema"),
            (_("Kids Mod"), "Kids"),
            (_("Korku Mod"), "Korku"),
            (_("Müzik Mod"), "Müzik")
        ]
        for idx, (label_text, key) in enumerate(mode_items):
            rb = QRadioButton(label_text)
            self.button_group.addButton(rb, idx)
            rb.toggled.connect(lambda checked, k=key: self._on_radio_toggled(k, checked))
            content_layout.addWidget(rb)
            self.mode_buttons[key] = rb

        # Varsayılan seçili mod
        self.mode_buttons['Normal'].setChecked(True)

        content_layout.addStretch(1)
        self.main_layout.addWidget(self.content_widget)

        self.content_widget.setMaximumHeight(0)
        self.content_widget.hide()
        self.is_collapsed = True
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(self.animation_duration)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _on_radio_toggled(self, key, checked):
        if checked:
            self.mode_changed.emit(key)

    def set_active_mode(self, key):
        """Dışarıdan (örneğin parola iptalinde) butonu tetikleme döngüsüne
        girmeden sessizce önceki moda geri çeker."""
        btn = self.mode_buttons.get(key)
        if btn:
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        if not self.is_collapsed:
            try:
                self.animation.finished.disconnect(self.content_widget.hide)
            except TypeError:
                pass 
            self.content_widget.setMaximumHeight(self.content_widget.sizeHint().height())
            self.animation.setStartValue(0)
            self.animation.setEndValue(self.content_widget.sizeHint().height())
            self.content_widget.show()
            self.toggle_button.setText(_("\u25b2 Mod Seçeneği"))
        else:
            self.animation.setStartValue(self.content_widget.height())
            self.animation.setEndValue(0)
            self.animation.finished.connect(self.content_widget.hide)
            self.toggle_button.setText(_("\u25bc Mod Seçeneği"))
        self.animation.start()

    
class FolderExplorerBox(QWidget):
    """Aktif modun kök dizininden başlayan, kendi içinde dikey kaydırılabilen
    küçük bir dosya gezgini."""
    dump_requested = pyqtSignal(str)  # dökülecek klasörün tam yolu

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_icon_label = QLabel()
        folder_icon = QIcon.fromTheme("folder")
        if folder_icon.isNull():
            folder_icon = QApplication.instance().style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        title_icon_label.setPixmap(folder_icon.pixmap(16, 16))
        title_row.addWidget(title_icon_label)

        title = QLabel(_("Klasörler"))
        title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        self.breadcrumb_label = QLabel("")
        self.breadcrumb_label.setWordWrap(True)
        self.breadcrumb_label.setStyleSheet("color: palette(mid); font-size: 9pt;")
        layout.addWidget(self.breadcrumb_label)

        self.folder_list = QListWidget()
        self.folder_list.setFixedHeight(208)
        self.folder_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.folder_list)

        self.dump_button = QPushButton(_("Dök"))
        self.dump_button.clicked.connect(self._on_dump_clicked)
        layout.addWidget(self.dump_button)

        self.root_dir = ""
        self.current_dir = ""

    def set_root(self, root_dir):
        """Aktif mod değiştiğinde (ya da ilk kurulumda) gezgini bu kökten başlatır."""
        self.root_dir = (root_dir or "").strip()
        self.current_dir = self.root_dir
        self.refresh()

    def refresh(self):
        self.folder_list.clear()
        if not self.current_dir or not os.path.isdir(self.current_dir):
            self.breadcrumb_label.setText(_("(Bu mod için geçerli bir dizin tanımlanmamış)"))
            return

        rel = os.path.relpath(self.current_dir, self.root_dir) if self.root_dir else ""
        self.breadcrumb_label.setText(_("Kök Dizin") if rel in ("", ".") else rel)

        style = QApplication.instance().style()

        # Kök dizinde değilsek, üst dizine çıkma satırını en üste ekleyelim.
        if self.root_dir and os.path.normpath(self.current_dir) != os.path.normpath(self.root_dir):
            up_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
            up_item = QListWidgetItem(up_icon, _("\u2b06 Üst Dizin"))
            up_item.setData(Qt.ItemDataRole.UserRole, "..")
            self.folder_list.addItem(up_item)

        try:
            all_entries = os.listdir(self.current_dir)
        except Exception as e:
            print(f"Klasör listeleme hatası: {e}")
            all_entries = []

        subfolders = sorted(e for e in all_entries if os.path.isdir(os.path.join(self.current_dir, e)))
        files = sorted(e for e in all_entries if os.path.isfile(os.path.join(self.current_dir, e)))

        folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        for name in subfolders:
            item = QListWidgetItem(folder_icon, name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.folder_list.addItem(item)

        # Dosyalar sadece bilgi amaçlı gösteriliyor: gri, tıklanamaz/seçilemez
        # (Dök mantığı sadece klasör seçimini dikkate alıyor, dosya satırları
        # yanlışlıkla "seçili" sayılıp kafa karıştırmasın diye)
        file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        for name in files:
            item = QListWidgetItem(file_icon, name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QApplication.instance().palette().mid())
            self.folder_list.addItem(item)

    def _on_item_double_clicked(self, item):
        target = item.data(Qt.ItemDataRole.UserRole)
        if target == "..":
            self._navigate_up()
        else:
            self._navigate_into(target)

    def _navigate_up(self):
        """Bir üst dizine çıkar. Bu metot sadece kökte DEĞİLKEN çağrılabildiği
        için (refresh() üst satırı sadece o durumda gösteriyor), kökten daha
        yukarı çıkma ihtimali yapı gereği zaten yok."""
        if not self.root_dir or not self.current_dir:
            return
        if os.path.normpath(self.current_dir) == os.path.normpath(self.root_dir):
            return
        self.current_dir = os.path.dirname(os.path.normpath(self.current_dir))
        self.refresh()

    def _navigate_into(self, folder_name):
        new_dir = os.path.join(self.current_dir, folder_name)
        if os.path.isdir(new_dir):
            self.current_dir = new_dir
            self.refresh()

    def _on_dump_clicked(self):
        """Seçili bir alt klasör varsa onu, yoksa (örn. en dipteki, alt
        klasörü olmayan bir dizindeysen) o an içinde bulunduğumuz klasörü döker."""
        item = self.folder_list.currentItem()
        target_name = item.data(Qt.ItemDataRole.UserRole) if item else None

        if target_name and target_name != "..":
            target_path = os.path.join(self.current_dir, target_name)
        else:
            target_path = self.current_dir

        if target_path and os.path.isdir(target_path):
            self.dump_requested.emit(target_path)

class SimpleVideoListBox(QWidget):
    """Klasörler kutusuna benzer, kendi kaydırma çubuğuna sahip, video
    adlarını listeleyen basit bir kutu. Bir isme tıklanınca video oynatılır."""
    video_clicked = pyqtSignal(str)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
        self.list_widget.setFixedHeight(117)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

    def set_videos(self, video_list):
        self.list_widget.clear()
        for v in video_list:
            name = v.get('name') or os.path.basename(v.get('path', ''))
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, v.get('path'))
            item.setToolTip(v.get('path', ''))
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.video_clicked.emit(path)

class VideoCardWidget(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, video_info, thumb_path=None, parent=None):
        super().__init__(parent)
        self.video_info = video_info
        self.video_path = video_info.get('path', '')
        self.thumb_path = thumb_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(240, 200)
        self.setStyleSheet(
            "VideoCardWidget { background-color: palette(base); border: 1px solid palette(mid); border-radius: 8px; } "
            "VideoCardWidget:hover { border: 1px solid palette(highlight); }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 16:9 Thumbnail Alanı
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(228, 128)
        self.thumb_label.setStyleSheet("background-color: #000; border-radius: 6px;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setScaledContents(True)
        layout.addWidget(self.thumb_label)

        # 2. Başlık Alanı
        title_text = video_info.get('name', os.path.basename(self.video_path))
        self.title_label = QLabel(title_text)
        self.title_label.setWordWrap(True)
        self.title_label.setFixedHeight(45)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        font = QFont("Arial", 9)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.title_label)

        # Küçük resim varsa hemen yükle, yoksa yer tutucu metin koy
        if self.thumb_path and os.path.exists(self.thumb_path):
            self.set_thumbnail(self.thumb_path)
        else:
            self.thumb_label.setText(_("Yükleniyor..."))
            self.thumb_label.setStyleSheet("background-color: #242424; color: #666; border-radius: 6px;")

    def set_thumbnail(self, thumb_path):
        """Arka planda üretilen veya var olan thumbnail'ı karta basar."""
        self.thumb_path = thumb_path
        if os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            self.thumb_label.setText("")
            self.thumb_label.setStyleSheet("background-color: #000; border-radius: 6px;")
            self.thumb_label.setPixmap(pixmap)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.video_path)
        super().mousePressEvent(event)


class RecommendedVideoCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, video_info, thumb_path=None, parent=None):
        super().__init__(parent)
        self.video_info = video_info
        self.video_path = video_info.get('path', '')
        self.thumb_path = thumb_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(72)
        self.setStyleSheet(
            "RecommendedVideoCard { background-color: palette(base); border: 1px solid palette(mid); border-radius: 6px; } "
            "RecommendedVideoCard:hover { background-color: palette(midlight); border: 1px solid palette(highlight); }"
        )

        h_layout = QHBoxLayout(self)
        h_layout.setContentsMargins(5, 5, 8, 5)
        h_layout.setSpacing(8)

        # Solda 16:9 Thumbnail alanı (106 x 60 px)
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(106, 60)
        self.thumb_label.setStyleSheet("background-color: #000000; border-radius: 4px;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setScaledContents(True)
        h_layout.addWidget(self.thumb_label)

        # Sağda Video Adı
        title_text = video_info.get('name', os.path.basename(self.video_path))
        self.title_label = QLabel(title_text)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        font = QFont("Arial", 9)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("border: none; background: transparent;")
        h_layout.addWidget(self.title_label, 1)

        self.is_active = False
        if self.thumb_path and os.path.exists(self.thumb_path):
            self.set_thumbnail(self.thumb_path)
        else:
            self.thumb_label.setText("...")
            self.thumb_label.setStyleSheet("background-color: #242424; color: #888; border-radius: 4px; font-size: 10px;")

    def set_active(self, is_active):
        """Oynatılan video kartını koyu ve sol kenarı vurgulu hale getirir."""
        self.is_active = is_active
        if is_active:
            self.setStyleSheet(
                "RecommendedVideoCard { background-color: palette(mid); border: 1px solid palette(highlight); border-left: 4px solid palette(highlight); border-radius: 6px; } "
                "RecommendedVideoCard:hover { background-color: palette(mid); }"
            )
        else:
            self.setStyleSheet(
                "RecommendedVideoCard { background-color: palette(base); border: 1px solid palette(mid); border-radius: 6px; } "
                "RecommendedVideoCard:hover { background-color: palette(midlight); border: 1px solid palette(highlight); }"
            )

    def set_thumbnail(self, thumb_path):
        self.thumb_path = thumb_path
        if os.path.exists(thumb_path):
            self.thumb_label.setText("")
            self.thumb_label.setStyleSheet("background-color: #000; border-radius: 4px;")
            self.thumb_label.setPixmap(QPixmap(thumb_path))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.video_path)
        super().mousePressEvent(event)


class SearchResultRow(RecommendedVideoCard):
    """RecommendedVideoCard'ın arama sonuçları için büyütülmüş hali —
    aynı solda-resim/sağda-başlık düzenini, daha büyük thumbnail ile kullanır."""
    def __init__(self, video_info, thumb_path=None, parent=None):
        super().__init__(video_info, thumb_path=thumb_path, parent=parent)
        self.setFixedHeight(100)
        self.thumb_label.setFixedSize(160, 90)


class ResponsiveVideoGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_min_width = 250
        self.current_columns = 4
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        self.grid_layout.setSpacing(15)
        for col in range(self.current_columns):
            self.grid_layout.setColumnStretch(col, 1)

        self.video_items = []
        self.cards_by_path = {}
        self._pending_videos = []
        self._pending_index = 0
        self._pending_total = 0
        self._pending_thumb_dir = None
        self._is_loading = False

    def set_videos(self, video_list, thumb_dir):
        """Tüm grid'i sıfırlar ve diskte binlerce video olsa dahi açılışın anında
        olması için sadece ilk 40 videoyu ekler."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.video_items.clear()
        self.cards_by_path.clear()

        self._pending_thumb_dir = thumb_dir
        self._pending_videos = list(video_list)
        random.shuffle(self._pending_videos)
        self._pending_total = len(self._pending_videos)
        self._pending_index = 0

        # Başlangıçta sadece ilk 40 kartı anında yükle
        self.load_more(count=40)

    def load_more(self, count=40):
        """Kullanıcı aşağı kaydırdıkça sıradaki videoları yükler."""
        if self._is_loading or self._pending_index >= self._pending_total:
            return
        self._is_loading = True

        thread_pool = QThreadPool.globalInstance()

        end = min(self._pending_index + count, self._pending_total)
        for i in range(self._pending_index, end):
            video_info = self._pending_videos[i]
            vpath = video_info.get('path', '')
            path_hash = hashlib.md5(vpath.encode('utf-8')).hexdigest()
            thumb_path = os.path.join(self._pending_thumb_dir, f"{path_hash}.jpg")

            card = VideoCardWidget(video_info, thumb_path=thumb_path, parent=self)
            card.clicked.connect(self._video_clicked)

            row = i // self.current_columns
            col = i % self.current_columns
            self.grid_layout.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

            self.video_items.append(card)
            self.cards_by_path[vpath] = card

            worker = ThumbnailWorker(vpath, thumb_path)
            worker.signals.finished.connect(self._on_thumb_ready)
            thread_pool.start(worker)

        self._pending_index = end
        self._is_loading = False

    def _on_thumb_ready(self, video_path, thumb_path):
        if video_path in self.cards_by_path:
            self.cards_by_path[video_path].set_thumbnail(thumb_path)

    def _video_clicked(self, video_path):
        parent_window = self.window()
        if isinstance(parent_window, QMainWindow) and hasattr(parent_window, 'play_video'):
            if parent_window.play_video(video_path):
                parent_window.stacked_widget.setCurrentIndex(1)

    def rearrange_grid(self, available_width):
        if not self.video_items:
            return

        # Geçerli genişliği belirle
        if available_width <= 200:
            parent_w = self.parent().width() if self.parent() else 0
            available_width = max(300, parent_w, self.width())

        # Sütun sayısını doğrudan 4'e sabitle
        new_columns = 4

        if new_columns == self.current_columns and self.grid_layout.count() > 0:
            return

        self.current_columns = new_columns

        # Grid üzerindeki tüm eski sütun esnekliklerini temizle
        for col in range(self.grid_layout.columnCount()):
            self.grid_layout.setColumnStretch(col, 0)

        # Elemanları grid'den sök ama silme (setParent'a dokunmadan söküyoruz)
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)

        # Kartları yeni sütun düzenine göre yeniden ekle
        for i, card in enumerate(self.video_items):
            row = i // self.current_columns
            col = i % self.current_columns
            self.grid_layout.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Sadece aktif sütunlara eşit genişlik esnekliği uygula
        for col in range(self.current_columns):
            self.grid_layout.setColumnStretch(col, 1)

        self.updateGeometry()

    def resizeEvent(self, event):
        self.rearrange_grid(self.width())
        super().resizeEvent(event)

    


class AspectRatioWidget(QWidget):
    geometry_changed = pyqtSignal()
    mouse_entered = pyqtSignal()
    mouse_left = pyqtSignal()

    def __init__(self, ratio=16/9, parent=None):
        super().__init__(parent)
        self.ratio = ratio
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(1)
        self.setMinimumWidth(1)
        self.setMouseTracking(True)
        self.content_layout = QHBoxLayout(self)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        self.inner_content = QWidget(self)
        self.inner_content.setMouseTracking(True)
        self.content_layout.addWidget(self.inner_content)
        
    def enterEvent(self, event):
        self.mouse_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.mouse_left.emit()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_geometry()

    def closeEvent(self, event):
        """Uygulama kapatılırken MPV C-kütüphanesi thread'lerini güvenle sonlandırır."""
        if hasattr(self, 'mpv_player') and self.mpv_player:
            try:
                self.mpv_player.terminate()
            except Exception:
                pass
        event.accept()

    def apply_geometry(self):
        """Video alanının geometrisini yeniden hesaplayıp uygular. Hem normal
        boyutlandırma olaylarından hem de dışarıdan (mpv yeni bir video
        yükleyip kendi iç ölçeğini değiştirmiş olabileceği anlarda) zorla
        çağrılabilir — böylece mpv ne yaparsa yapsın, doğru geometri her
        zaman bizim elimizde kalır."""
        width = self.width()
        height = int(width / self.ratio)

        # Video, kontrol çubuğu/seek çubuğu/başlık için ayrılan alanı asla
        # yutmamalı. Özellikle tam ekranda genişlik çok arttığında (kenar
        # menüsü/panel gizlenince) oran gereği yükseklik de aşırı büyüyüp
        # altındaki kontrolleri ekran dışına itebiliyordu; bunu, pencere
        # yüksekliğinden kontroller için makul bir pay ayırarak engelliyoruz.
        top_level = self.window()
        comment_area = getattr(top_level, 'comment_placeholder_container', None)
        if comment_area is None or comment_area.isVisible():
            # Başlık + Seek + Butonlar + Puan/İzlendi + Yorum Kutusu için ayrılan pay
            reserved_for_controls = 250  # Normal pencere modu
        else:
            # Tam ekran: seek/ses çubuğu şu an gösteriliyorsa video küçülüp
            # ona gerçek (taşmayan) bir yer açsın; gösterilmiyorsa video
            # tam ekranı tamamen kaplasın.
            reserved_for_controls = 50 if getattr(top_level, '_fullscreen_bar_visible', False) else 0
        if top_level:
            max_height = max(100, top_level.height() - reserved_for_controls)
            if height > max_height:
                height = max_height
                width = int(height * self.ratio)

        self.setFixedHeight(height)
        x = (self.width() - width) // 2
        self.inner_content.setGeometry(x, 0, width, height)

        try:
            self.geometry_changed.emit()
        except Exception:
            pass

    def mousePressEvent(self, event):
        """Tıklamayı yakala; inner_content alanına sol tıklama yapılırsa oynat/duraklat değiştir."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self.inner_content.geometry().contains(pos):
                parent_window = self.window()
                if parent_window and hasattr(parent_window, '_toggle_pause'):
                    parent_window._toggle_pause()
        super().mousePressEvent(event)


class ClickableSlider(QSlider):
    """Groove'un herhangi bir noktasına tıklandığında kulakçığı sürüklemeye
    gerek kalmadan doğrudan o konuma atlayan QSlider."""

    def _value_from_pos(self, pos):
        handle_length = 12
        if self.orientation() == Qt.Orientation.Horizontal:
            span = self.width() - handle_length
            coord = pos.x() - handle_length // 2
        else:
            span = self.height() - handle_length
            coord = pos.y() - handle_length // 2
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), coord, max(1, span))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            value = self._value_from_pos(event.position().toPoint())
            self.setSliderDown(True)
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            value = self._value_from_pos(event.position().toPoint())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ThisIsMyTubeApp(QMainWindow):
    _fullscreen_toggle_requested = pyqtSignal()
    _volume_ui_update_requested = pyqtSignal(int)
    _time_ui_update_requested = pyqtSignal(int)
    _single_click_requested = pyqtSignal()
    _eof_reached_signal = pyqtSignal()
    # --- Sabitler ---
    VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.webm', '.flv', '.mov', '.wmv')

    def __init__(self):
        super().__init__()
        
        self.CONFIG_PATH = os.path.expanduser('~/.config/thisismytube')
        self.THUMB_PATH = os.path.join(self.CONFIG_PATH, "thumbnails")
        os.makedirs(self.THUMB_PATH, exist_ok=True)
        self.active_menu_id = "home" 
        self.icon_path = None 
        self.found_videos = [] 
        self.current_mode = "Normal"
        self.current_language = "en"
        self._player_view_active = False
        self.playback_history = []
        self._is_navigating_back = False
        self.auth_manager = AuthManager(self.CONFIG_PATH)

        self._setup_config_files() 
        self._set_app_icon()      
        
        self.setWindowTitle("ThisisMyTube - This is your tube!")
        self.setGeometry(100, 100, 1000, 700) 
        self.setMinimumSize(800, 600) 
        
        # --- MPV Gömme için Öncül Widget Kurulumu (DEĞİŞİKLİK BURADA) ---
        self.mpv_player_area = self._setup_mpv_widget()
        
        # --- MPV Oynatıcı Kurulumu ---
        self.mpv_player = mpv.MPV(
            vo='gpu', 
            loop=False, 
            keep_open=True,
            input_default_bindings=True, 
            osc=False, 
            idle=True, 
            volume=80,  # Başlangıç ses seviyesi
            # Videolar arası ses seviyesi farkını (5.1->stereo downmix, farklı
            # kaynak/master seviyeleri) otomatik dengelemek için dinamik
            # loudness normalizasyonu filtresi:
            # f ve g büyütülerek filtre çok daha yavaş/yumuşak tepki veriyor
            # (video içindeki doğal ses iniş çıkışlarını "pompalamasın" diye);
            # m ile de en fazla ne kadar yükseltme yapabileceği sınırlanıyor.
            af='lavfi=[dynaudnorm=f=500:g=31:m=7]',
            log_file=os.path.join(self.CONFIG_PATH, "mpv.log"),
            wid=int(self.mpv_area_widget.winId()) # WID'yi constructor içinde ayarla
        )
        self.mpv_player.observe_property('pause', self._mpv_pause_changed)
        self.mpv_player.observe_property('volume', self._mpv_volume_changed)
        self.mpv_player.observe_property('mute', self._mpv_mute_changed)
        self.mpv_player.observe_property('video-params', self._on_video_params_changed)
        self.mpv_player.observe_property('fullscreen', self._on_mpv_dbl_click_fullscreen)
        self.mpv_player.observe_property('eof-reached', self._on_mpv_eof_reached)
        self.mpv_player.on_key_press('mbtn_left')(lambda: self._single_click_requested.emit())
        self._fullscreen_toggle_requested.connect(self._on_fullscreen_toggle_safe)
        self._volume_ui_update_requested.connect(self._apply_volume_ui)
        self._time_ui_update_requested.connect(self._apply_time_ui)
        self._single_click_requested.connect(self._on_video_single_click)
        self._eof_reached_signal.connect(self._on_eof_reached_safe)
        # Seek bar bindings: observe current time and duration
        try:
            self.mpv_player.observe_property('time-pos', self._mpv_time_changed)
            self.mpv_player.observe_property('duration', self._mpv_duration_changed)
        except Exception:
            # Some mpv builds may not support observe_property in the same way; ignore failures
            pass
        
        # --- UI Kurulumu ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.settings_menu = self._create_settings_menu()
        self.header_frame = self._create_header()
        settings_menu = self.settings_menu
        header_frame = self.header_frame
        
        self.home_page = self._create_home_view()
        # Önceden oluşturulmuş player_area'yı gönderiyoruz
        self.player_view = self._create_player_view(self.mpv_player_area) 
        
        # Player view oluşturulduktan sonra QWidget'in winId'si mpv'ye atanır.
        # Bu satır artık yukarıdaki constructor içinde yapıldığı için KALDIRILDI.
        # self.mpv_player.set_property('wid', self.mpv_area_widget.winId()) 

        self.disk_scan_settings_view = self._create_disk_scan_settings_view()
        self.settings_view = SettingsView(self)
        self.settings_view.backup_requested.connect(self._handle_backup)
        self.settings_view.restore_requested.connect(self._handle_restore)
        self.settings_view.reset_requested.connect(self._handle_reset)
        self.settings_view.clear_cache_requested.connect(self._handle_clear_cache)
        if hasattr(self.settings_view, 'language_changed'):
            self.settings_view.language_changed.connect(self._on_language_changed_from_ui)
        self.about_view = self._create_about_view()

        self.folder_result_page = self._create_folder_result_view()
        self.search_result_page = self._create_search_result_view()

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.home_page)               # 0: Ana Sayfa
        self.stacked_widget.addWidget(self.player_view)              # 1: Video Oynatıcı
        self.stacked_widget.addWidget(self.disk_scan_settings_view) # 2: İndeksleme
        self.stacked_widget.addWidget(self.settings_view)           # 3: Ayarlar
        self.stacked_widget.addWidget(self.about_view)               # 4: About
        self.stacked_widget.addWidget(self.folder_result_page)       # 5: Klasör Dökümü
        self.stacked_widget.addWidget(self.search_result_page)       # 6: Arama Sonuçları
        self.stacked_widget.currentChanged.connect(self._on_stacked_page_changed)

        self.sidebar_scroll_area = self._create_sidebar(num_items=10)

        self.main_layout.addWidget(settings_menu)
        
        center_right_container = QWidget()
        center_right_layout = QVBoxLayout(center_right_container)
        center_right_layout.setContentsMargins(0, 0, 0, 0)
        
        center_right_layout.addWidget(header_frame)
        
        player_and_sidebar_area = QHBoxLayout()

        player_and_sidebar_area.addWidget(self.stacked_widget, 5) 
        player_and_sidebar_area.addWidget(self.sidebar_scroll_area, 2)

        center_right_layout.addLayout(player_and_sidebar_area)
        self.main_layout.addWidget(center_right_container, 5)

        self.stacked_widget.setCurrentIndex(0) 
        self._update_menu_style() 

        # Pencere ekrana çizildikten hemen sonra (50ms) verileri yükle
        QTimer.singleShot(50, self._load_persistent_data) 

    # ------------------------------------
    # --- MPV Kontrol Metotları ---
    # ------------------------------------
    def play_video(self, path):
        """Verilen yoldaki videoyu oynatıcıda yükler, başlığı günceller ve
        sağ listede seçili yapar. Dosya artık yoksa (silinmiş/taşınmış)
        dostane bir uyarı gösterip False döner — çağıran taraf bu durumda
        oynatıcı sayfasına GEÇMEMELİ."""
        if not os.path.exists(path):
            QMessageBox.warning(
                self, _("Video Bulunamadı"),
                _("Oynatmayı denediğiniz videoya erişilemiyor. Adı değiştirilmiş, "
                  "taşınmış ya da silinmiş olabilir. Yeni bir indeks taraması "
                  "yapmanız önerilir. Bu taramadan sonra tüm dosyalara sorunsuzca "
                  "erişebilirsiniz.")
            )
            return False

        # Yeni bir video açıldığında mevcut videoyu geçmişe kaydet
        current = getattr(self, 'current_playing_path', None)
        if not getattr(self, '_is_navigating_back', False) and current and os.path.abspath(current) != os.path.abspath(path):
            self.playback_history.append(current)
            if len(self.playback_history) > 100:  # Bellek şişmesin diye son 100 videoyu tutar
                self.playback_history.pop(0)

        self.current_playing_path = path
        self._current_duration = 0
        self._update_time_display(0)
        self._update_prev_btn_state()
        self.mpv_player.play(path)
        self.mpv_player.pause = False

        # 1. Video başlığını güncelle (Uzantısız dosya adı)
        clean_title = os.path.splitext(os.path.basename(path))[0]
        for v in self.found_videos:
            if os.path.abspath(v.get('path', '')) == os.path.abspath(path):
                clean_title = os.path.splitext(v.get('name', clean_title))[0]
                break
        if hasattr(self, 'player_title_label'):
            self.player_title_label.setText(clean_title)

        # 2. Sağdaki listede oynatılan videoyu koyu/aktif işaretle
        self._highlight_active_sidebar_card(path)

        # 3. Puan/izlenme/not widget'larını bu videonun kayıtlı değerlerine göre güncelle
        info = self._find_current_video_info()
        if hasattr(self, 'rating_widget'):
            self.rating_widget.set_rating(info.get('rating', 0) if info else 0)
        if hasattr(self, 'watched_checkbox'):
            self.watched_checkbox.blockSignals(True)
            self.watched_checkbox.setChecked(bool(info.get('watched', False)) if info else False)
            self.watched_checkbox.blockSignals(False)
        if hasattr(self, 'video_notes_edit'):
            self.video_notes_edit.blockSignals(True)
            self.video_notes_edit.setPlainText(info.get('notes', '') if info else '')
            self.video_notes_edit.blockSignals(False)

        return True

    def _update_prev_btn_state(self):
        """Geçmişte video varsa 'Önceki' butonunu aktif, yoksa pasif yapar."""
        if hasattr(self, 'prev_btn'):
            self.prev_btn.setEnabled(len(self.playback_history) > 0)

    def _play_prev_video(self):
        """Geçmiş listesindeki bir önceki videoya geri döner."""
        if self.playback_history:
            prev_path = self.playback_history.pop()
            self._is_navigating_back = True
            self.play_video(prev_path)
            self._is_navigating_back = False
            self._update_prev_btn_state()

    def _play_next_video(self):
        """Aktif moddaki videolardan mevcut olan hariç rastgele birini seçip oynatır."""
        candidates = self._filtered_videos_for_mode()
        current_path = getattr(self, 'current_playing_path', None)
        other_videos = [v for v in candidates if os.path.abspath(v.get('path', '')) != os.path.abspath(current_path or '')]

        pool = other_videos if other_videos else candidates
        if pool:
            next_video = random.choice(pool)
            self.play_video(next_video.get('path', ''))

    def _on_mpv_eof_reached(self, name, value):
        """MPV arka plan thread'i: Video sonuna ulaşıldığında sinyal yayar."""
        if value is True:
            self._eof_reached_signal.emit()

    def _on_eof_reached_safe(self):
        """Ana thread: Video bittiğinde otomatik oynatma açıksa sıradaki videoya geçer."""
        # Yeni video yüklenirken oluşabilecek mükerrer tetiklemeleri önlemek için kısa kilit
        if getattr(self, '_loading_next_video', False):
            return

        if hasattr(self, 'autoplay_checkbox') and self.autoplay_checkbox.isChecked():
            self._loading_next_video = True
            self._play_next_video()
            # 1 saniye sonra kilidi kaldır
            QTimer.singleShot(1000, lambda: setattr(self, '_loading_next_video', False))

    def _highlight_active_sidebar_card(self, active_path):
        """Sağ panelde oynatılan videonun kartını seçili yapar, diğerlerini normale çeker."""
        if hasattr(self, 'sidebar_cards_by_path'):
            for vpath, card in self.sidebar_cards_by_path.items():
                card.set_active(os.path.abspath(vpath) == os.path.abspath(active_path))

    def _find_current_video_info(self):
        """Şu an oynatılan videonun found_videos içindeki kaydını döner."""
        path = getattr(self, 'current_playing_path', None)
        if not path:
            return None
        for v in self.found_videos:
            if v.get('path') == path:
                return v
        return None

    def _on_watched_changed(self, state):
        info = self._find_current_video_info()
        if info is not None:
            info['watched'] = (state == Qt.CheckState.Checked.value)
            self._save_persistent_data()
            self._update_watched_and_favorites_lists()

    def _on_autoplay_toggled(self, checked):
        """Otomatik oynatma tercihi değiştiğinde settings.json'a kaydeder."""
        self._save_persistent_data()

    def _on_rating_changed(self, value):
        info = self._find_current_video_info()
        if info is not None:
            info['rating'] = value
            self._save_persistent_data()
            self._update_watched_and_favorites_lists()

    def _on_video_notes_changed(self):
        info = self._find_current_video_info()
        if info is not None and hasattr(self, 'video_notes_edit'):
            info['notes'] = self.video_notes_edit.toPlainText()
            self._save_persistent_data()
        
    def _on_fullscreen_toggle_safe(self):
        """Çift tıklama gerçek bir tam ekran geçişine dönüştüğünde, bekleyen
        (henüz uygulanmamış) tek-tıklama pause'unu iptal ediyoruz — böylece
        çift tıklama hem tam ekrana geçip hem de videoyu istemeden
        duraklatmıyor."""
        if hasattr(self, '_single_click_timer'):
            self._single_click_timer.stop()
        self._toggle_fullscreen()

    def _on_video_single_click(self):
        """Videoya tek tıklandığında hemen pause yapmak yerine, bunun bir
        çift tıklamanın (tam ekran) ilk parçası olmadığından emin olmak için
        kısa bir süre bekliyoruz."""
        if not hasattr(self, '_single_click_timer'):
            self._single_click_timer = QTimer(self)
            self._single_click_timer.setSingleShot(True)
            self._single_click_timer.timeout.connect(self._toggle_pause)
        self._single_click_timer.start(180)

    def _toggle_pause(self):
        """Oynat/Duraklat durumunu değiştirir."""
        if self.mpv_player:
            self.mpv_player.pause = not self.mpv_player.pause

    def _toggle_fullscreen(self):
        """Pencereyi tam ekran yapar/eski haline döndürür. MPV gömülü
        çalıştığından kendi 'fs' özelliğinin bir etkisi yok; tam ekranı
        Qt penceresi seviyesinde, çerçeve öğelerini (menü, başlık, sağ
        panel) gizleyerek yapıyoruz."""
        entering_fullscreen = not self.isFullScreen()

        if hasattr(self, 'settings_menu'):
            self.settings_menu.setVisible(not entering_fullscreen)
        if hasattr(self, 'header_frame'):
            self.header_frame.setVisible(not entering_fullscreen)
        if hasattr(self, 'sidebar_scroll_area'):
            self.sidebar_scroll_area.setVisible(not entering_fullscreen)
            # setVisible tek başına yetmeyebiliyor: setMinimumWidth(280) ile
            # verilmiş sabit bir alt sınır var, gizliyken bile layout'ta
            # hayalet bir pay bırakabiliyor. Genişliği de zorla sıfırlayıp
            # çıkışta eski haline döndürüyoruz.
            if entering_fullscreen:
                self.sidebar_scroll_area.setMaximumWidth(0)
            else:
                self.sidebar_scroll_area.setMaximumWidth(16777215)
        if hasattr(self, 'comment_placeholder_container'):
            self.comment_placeholder_container.setVisible(not entering_fullscreen)
        if hasattr(self, 'player_title_label'):
            self.player_title_label.setVisible(not entering_fullscreen)
        if hasattr(self, 'playback_controls_widget'):
            self.playback_controls_widget.setVisible(not entering_fullscreen)
        if hasattr(self, 'speed_controls_widget'):
            self.speed_controls_widget.setVisible(not entering_fullscreen)
        if hasattr(self, 'rating_row_widget'):
            self.rating_row_widget.setVisible(not entering_fullscreen)
        if hasattr(self, 'player_view_layout'):
            if entering_fullscreen:
                self.player_view_layout.setContentsMargins(0, 0, 0, 0)
            else:
                self.player_view_layout.setContentsMargins(10, 8, 10, 10)
        if entering_fullscreen:
            # Tam ekrana yeni girerken, fare hareket edene kadar seek/ses da gizli kalsın
            self._fullscreen_bar_visible = False
            if hasattr(self, 'seek_container'):
                self.seek_container.setVisible(False)
            if hasattr(self, 'volume_controls_widget'):
                self.volume_controls_widget.setVisible(False)
        else:
            # Tam ekrandan çıkarken seek/ses her zaman görünür olmalı (normal mod kuralı)
            if hasattr(self, 'seek_container'):
                self.seek_container.setVisible(True)
            if hasattr(self, 'volume_controls_widget'):
                self.volume_controls_widget.setVisible(True)

        if entering_fullscreen:
            # Tam ekrana girmeden önceki hali (büyütülmüş müydü?) hatırlanıyor
            # ki çıkışta showNormal() ile yanlışlıkla küçük pencereye dönmeyelim.
            self._was_maximized_before_fullscreen = self.isMaximized()
            self.showFullScreen()
        else:
            if getattr(self, '_was_maximized_before_fullscreen', False):
                self.showMaximized()
            else:
                self.showNormal()

        if hasattr(self, 'fullscreen_btn'):
            if entering_fullscreen:
                self.fullscreen_btn.setIcon(self._theme_icon("view-restore", QStyle.StandardPixmap.SP_TitleBarNormalButton))
            else:
                self.fullscreen_btn.setIcon(self._theme_icon("view-fullscreen", QStyle.StandardPixmap.SP_TitleBarMaxButton))

        # Tam ekrana giriş ve çıkışta video ölçeğini pencereye göre anında yeniden hesaplat
        if hasattr(self, 'mpv_player_area'):
            QTimer.singleShot(50, self.mpv_player_area.apply_geometry)

    def keyPressEvent(self, event):
        """Boşluk = pause/play, Esc (tam ekrandaysak) = tam ekrandan çık."""
        if event.key() == Qt.Key.Key_Space:
            self._toggle_pause()
            return
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def _open_video_folder(self):
        """Oynatılmakta olan videonun bulunduğu klasörü, sistemin öntanımlı
        dosya yöneticisiyle açar."""
        path = getattr(self, 'current_playing_path', None)
        if not path or not os.path.exists(path):
            QMessageBox.information(self, _("Bilgi"), _("Şu anda oynatılan bir video yok."))
            return
        folder = os.path.dirname(os.path.abspath(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _toggle_mute(self):
        """Sesi kapatma/açma durumunu değiştirir."""
        if self.mpv_player:
            self.mpv_player.mute = not self.mpv_player.mute

    def _on_mpv_dbl_click_fullscreen(self, name, value):
        """mpv'nin varsayılan çift-tıklama bağlaması (MBTN_LEFT_DBL) kendi
        (gömülü modda işlevsiz) 'fullscreen' özelliğini değiştirdiğinde,
        bunu bizim gerçek Qt tam ekran geçişimiz için tetikleyici olarak
        kullanıyoruz. ÖNEMLİ: Bu geri çağırma mpv'nin kendi arka plan
        thread'inde çalışıyor — Qt arayüzüne buradan DOĞRUDAN dokunmak
        çökmeye yol açıyordu; bu yüzden sadece bir sinyal yolluyoruz, asıl
        işi (_toggle_fullscreen) Qt bunu ana thread'e güvenle taşıdıktan
        sonra yapıyor."""
        if value:
            self.mpv_player.fullscreen = False
            self._fullscreen_toggle_requested.emit()

    def _on_video_params_changed(self, name, value):
        """Yeni bir video yüklenip gerçek boyutları öğrenildiğinde, mpv'nin
        olası bir iç ölçekleme tuhaflığına karşı video alanının doğru
        geometrisini zorla yeniden uygular (özellikle tam ekranda, kare/dikey
        videolarda kontrolleri ezme sorununa karşı savunma amaçlı)."""
        if hasattr(self, 'mpv_player_area'):
            QTimer.singleShot(0, self.mpv_player_area.apply_geometry)

    def _mpv_mute_changed(self, name, value):
        """MPV'nin 'mute' özelliği değiştiğinde buton ikonunu günceller."""
        if hasattr(self, 'mute_btn'):
            if value:
                self.mute_btn.setIcon(self._theme_icon("audio-volume-muted", QStyle.StandardPixmap.SP_MediaVolumeMuted))
            else:
                self.mute_btn.setIcon(self._theme_icon("audio-volume-high", QStyle.StandardPixmap.SP_MediaVolume))

    def _on_speed_combo_changed(self, text):
        """Açılır listeden seçilen hızı MPV'ye uygular."""
        if self.mpv_player:
            try:
                speed_val = float(text.replace('x', '').strip())
                self.mpv_player.speed = speed_val
            except ValueError:
                pass

    def _set_player_volume(self, value):
        """MPV ses seviyesini doğrusal 0-100 aralığında ayarlar."""
        if self.mpv_player:
            # mpv doğrudan 0-100 linear volume destekler
            self.mpv_player.volume = max(0, min(100, int(value)))
            if hasattr(self, 'volume_label'):
                self.volume_label.setText(f"%{int(value)}")

    def _mpv_pause_changed(self, name, value):
        """MPV'nin 'pause' özelliği değiştiğinde arayüzü günceller."""
        if hasattr(self, 'play_pause_btn'):
            if value: # Duraklatıldı (Oynat simgesi göster)
                self.play_pause_btn.setIcon(self._theme_icon("media-playback-start", QStyle.StandardPixmap.SP_MediaPlay))
            else: # Oynatılıyor (Duraklat simgesi göster)
                self.play_pause_btn.setIcon(self._theme_icon("media-playback-pause", QStyle.StandardPixmap.SP_MediaPause))
    
    def _mpv_volume_changed(self, name, value):
        """MPV'nin ses seviyesi değiştiğinde çağrılır. ÖNEMLİ: Bu, mpv'nin
        kendi arka plan thread'inde çalışıyor — Qt arayüzüne (slider/label)
        buradan DOĞRUDAN dokunmak, tam ekran çökmesinde gördüğümüz türden bir
        thread-güvenliği sorunu (bu sefer çökme değil, senkron olmayan
        görüntü olarak kendini gösteriyordu). Bu yüzden sadece bir sinyal
        yolluyoruz; asıl arayüz güncellemesi ana thread'de yapılıyor.
        """
        if value is not None:
            self._volume_ui_update_requested.emit(int(value))

    def _apply_volume_ui(self, value):
        """_mpv_volume_changed'in ana thread'e güvenle taşıdığı asıl arayüz
        güncellemesi."""
        if hasattr(self, 'volume_slider') and hasattr(self, 'volume_label'):
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(value)
            self.volume_slider.blockSignals(False)
            self.volume_label.setText(str(value))

    def _mpv_time_changed(self, name, value):
        """MPV arka plan thread'i: Zaman değiştiğinde UI thread'ine güvenli sinyal atar."""
        if value is not None:
            self._time_ui_update_requested.emit(int(value))

    def _apply_time_ui(self, current_seconds):
        """Ana UI thread'i: Slider'ı ve süreyi anlık olarak tazeler."""
        if not hasattr(self, 'seek_slider'):
            return
        if self.seek_slider.isSliderDown():
            return
        try:
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(current_seconds)
            self.seek_slider.blockSignals(False)
            self._update_time_display(current_seconds)
        except Exception:
            pass

    def _mpv_duration_changed(self, name, value):
        """MPV'den gelen süre bilgisini slider aralığına uygular."""
        if not hasattr(self, 'seek_slider') or value is None:
            return
        try:
            dur = int(value)
            if dur > 0:
                self._current_duration = dur
                self.seek_slider.setRange(0, dur)
                self._update_time_display(self.seek_slider.value())
        except Exception:
            pass

    def _on_seek_moved(self, value):
        """Kullanıcı slider'ı sürüklerken anlık zaman gösterimi güncellensin."""
        self._update_time_display(int(value))

    def _on_seek_released(self):
        """Kullanıcı slider'ı bıraktığında mpv'ye atla."""
        if not hasattr(self, 'seek_slider') or not self.mpv_player:
            return
        try:
            self.seek_slider.setSliderDown(False)
            val = int(self.seek_slider.value())
            self.mpv_player.seek(val, reference='absolute', precision='exact')
            self._update_time_display(val)
        except Exception as e:
            print(f"Seek hatası: {e}")

    def _format_time(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _update_time_display(self, current_seconds):
        """Zaman etiketini 'geçerli_süre / toplam_süre' formatında yazar."""
        if not hasattr(self, 'seek_time_label'):
            return
        cur_str = self._format_time(int(current_seconds or 0))
        dur_seconds = getattr(self, '_current_duration', 0)
        dur_str = self._format_time(int(dur_seconds)) if dur_seconds > 0 else "00:00"
        self.seek_time_label.setText(f"{cur_str} / {dur_str}")

    def _on_stacked_page_changed(self, index):
        """Sayfa değiştiğinde oynatmayı, hover takibini ve sidebar görünürlüğünü aktif sayfaya göre günceller."""
        self._player_view_active = (index == 1)
        
        if hasattr(self, 'sidebar_scroll_area'):
            self.sidebar_scroll_area.setVisible(index in (0, 1))

        if index == 0 and hasattr(self, 'home_video_grid'):
            QTimer.singleShot(50, lambda: self.home_video_grid.rearrange_grid(self.home_video_grid.width()))

        if self._player_view_active:
            # Video sayfasına geçildiğinde seek çubuğunu görünür başlat ve takibi aç
            self._show_seek_bar()
            if hasattr(self, 'hover_poll_timer'):
                self.hover_poll_timer.start(150)
        else:
            if hasattr(self, 'hover_poll_timer'):
                self.hover_poll_timer.stop()
            if self.mpv_player:
                self.mpv_player.pause = True

    # ------------------------------------
    # --- Thumbnail & Disk Tarama Mantığı ---
    # ------------------------------------
    def _generate_thumbnail(self, video_path):
        """FFmpeg kullanarak videonun 5. saniyesinden küçük resim üretir."""
        path_hash = hashlib.md5(video_path.encode('utf-8')).hexdigest()
        thumb_file = os.path.join(self.THUMB_PATH, f"{path_hash}.jpg")
        
        # Eğer thumbnail zaten varsa tekrar üretme
        if os.path.exists(thumb_file):
            return thumb_file

        try:
            # 5. saniyeden tek kare al, 320px genişliğe ölçekle
            cmd = [
                "ffmpeg", "-y",
                "-ss", "00:00:05",
                "-i", video_path,
                "-vframes", "1",
                "-vf", "scale=320:-1",
                "-q:v", "3",
                thumb_file
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if os.path.exists(thumb_file):
                return thumb_file
        except Exception:
            pass
        return None

    def _start_disk_scan(self):
        """Kullanıcının belirlediği dizinleri tarar ve video dosyalarını bulur."""
        # Yeniden tarama, kullanıcının verdiği puan/izlenme bilgisini SİLMESİN
        # diye, taramadan önce mevcut veriyi yola göre yedekliyoruz.
        _old_by_path = {v.get('path', ''): v for v in self.found_videos}
        self.found_videos = []
        
        def _get_dir_list(line_edit):
            text = line_edit.text().strip() if hasattr(self, line_edit) else ""
            return [text] if text and os.path.isdir(text) else []

        base_dir_text = self.base_dirs_line_edit.text().strip() if hasattr(self, 'base_dirs_line_edit') else ""
        if not base_dir_text or not os.path.isdir(base_dir_text):
            self.scan_results_label.setText("Hata: Lütfen geçerli bir taranacak ana dizin belirtin.")
            return

        base_dirs = [base_dir_text]
        adult_dirs = [self.adult_dirs_line_edit.text().strip()] if hasattr(self, 'adult_dirs_line_edit') and self.adult_dirs_line_edit.text().strip() else []
        dizi_dirs = [self.dizi_dirs_line_edit.text().strip()] if hasattr(self, 'dizi_dirs_line_edit') and self.dizi_dirs_line_edit.text().strip() else []
        sinema_dirs = [self.sinema_dirs_line_edit.text().strip()] if hasattr(self, 'sinema_dirs_line_edit') and self.sinema_dirs_line_edit.text().strip() else []
        kids_dirs = [self.kids_dirs_line_edit.text().strip()] if hasattr(self, 'kids_dirs_line_edit') and self.kids_dirs_line_edit.text().strip() else []
        korku_dirs = [self.korku_dirs_line_edit.text().strip()] if hasattr(self, 'korku_dirs_line_edit') and self.korku_dirs_line_edit.text().strip() else []
        muzik_dirs = [self.muzik_dirs_line_edit.text().strip()] if hasattr(self, 'muzik_dirs_line_edit') and self.muzik_dirs_line_edit.text().strip() else []

        total_files = 0
        total_videos = 0

        self.scan_results_label.setText("Tarama Başlatıldı... Lütfen bekleyin.")
        QApplication.processEvents() # UI'ı hemen güncelle

        mode_map = {
            "Adult": adult_dirs,
            "Dizi": dizi_dirs,
            "Sinema": sinema_dirs,
            "Kids": kids_dirs,
            "Korku": korku_dirs,
            "Müzik": muzik_dirs
        }

        # Ana Dizin'in DIŞINDA kalan (onun alt klasörü olmayan) mod
        # dizinlerini tespit edelim; bunları ayrıca, kendi başlarına
        # tarayacağız. Zaten Ana Dizin'in altındaysa dokunmuyoruz, çünkü
        # aşağıdaki Ana Dizin taraması onu doğru şekilde etiketleyecek.
        extra_roots = []  # (dizin_yolu, mod_adı)
        for mode_name, dirs in mode_map.items():
            for mdir in dirs:
                if not os.path.isdir(mdir):
                    continue
                is_nested_in_base = any(
                    os.path.isdir(b) and os.path.commonpath([mdir, b]) == b for b in base_dirs
                )
                if not is_nested_in_base:
                    extra_roots.append((mdir, mode_name))

        seen_paths = set()

        def _scan_root(root_dir, forced_mode=None):
            nonlocal total_files, total_videos
            for root, _, files in os.walk(root_dir):
                if forced_mode:
                    mode_by_dir = forced_mode
                else:
                    mode_by_dir = "Normal"
                    for mode_name, dirs in mode_map.items():
                        if any(os.path.isdir(mdir) and os.path.commonpath([root, mdir]) == mdir for mdir in dirs):
                            mode_by_dir = mode_name
                            break

                for file in files:
                    total_files += 1
                    if file.lower().endswith(self.VIDEO_EXTENSIONS):
                        video_path = os.path.join(root, file)
                        abs_path = os.path.abspath(video_path)
                        if abs_path in seen_paths:
                            continue  # Aynı dosya iki farklı kökten iki kez sayılmasın
                        seen_paths.add(abs_path)
                        total_videos += 1
                        self.found_videos.append({
                            'path': video_path,
                            'name': file,
                            'mode': mode_by_dir,
                            'is_adult': (mode_by_dir == "Adult"),
                            'rating': 0,
                            'watched': False,
                            'notes': ''
                        })

        for base_dir in base_dirs:
            if not os.path.isdir(base_dir):
                print(f"Uyarı: {base_dir} geçerli bir dizin değil.")
                continue
            _scan_root(base_dir)

        # Ana Dizin'in dışında kalan mod klasörlerini de kendi modlarıyla tara
        for extra_dir, mode_name in extra_roots:
            _scan_root(extra_dir, forced_mode=mode_name)


        # Hâlâ diskte olan videolar için, önceki puan/izlenme/not bilgisini
        # (varsa) yeni kayıtlara geri taşı.
        for v in self.found_videos:
            old = _old_by_path.get(v.get('path', ''))
            if old:
                v['rating'] = old.get('rating', 0)
                v['watched'] = old.get('watched', False)
                v['notes'] = old.get('notes', '')

        # Sonuç metnini hazırla
        result_text = _("Tarama Tamamlandı!") + "\n"
        result_text += _("Toplam Dosya Sayısı: {count}").format(count=total_files) + "\n"
        result_text += _("Bulunan Video Sayısı: {count}").format(count=total_videos) + "\n"
        mode_counts = {
            _("Private Mod"): len([v for v in self.found_videos if v['mode'] == "Adult"]),
            _("Dizi Mod"): len([v for v in self.found_videos if v['mode'] == "Dizi"]),
            _("Sinema Mod"): len([v for v in self.found_videos if v['mode'] == "Sinema"]),
            _("Kids Mod"): len([v for v in self.found_videos if v['mode'] == "Kids"]),
            _("Korku Mod"): len([v for v in self.found_videos if v['mode'] == "Korku"]),
            _("Müzik Mod"): len([v for v in self.found_videos if v['mode'] == "Müzik"])
        }
        for k, v in mode_counts.items():
            result_text += f"{k}: {v} \n"

        self.scan_results_label.setText(result_text)

        # Videoları Ana Sayfa gridine rassal (random) şekilde, sadece aktif
        # moddaki videoları filtreleyerek yükle
        if hasattr(self, 'home_page_stack'):
            self.home_page_stack.setCurrentIndex(0)
        if hasattr(self, 'home_video_grid'):
            self.home_video_grid.set_videos(self._filtered_videos_for_mode(), self.THUMB_PATH)

        # Önerilen videolar yan panelini rastgele kartlarla güncelle
        self._update_recommended_videos()

        # Yeni bulunan videoları ve ayarları hemen JSON dosyalarına kaydet
        self._save_persistent_data()
        self._update_mode_info_label()
        self._update_watched_and_favorites_lists()
        
        if self.found_videos:
             QMessageBox.information(
                 self, _("Tarama Başarılı"),
                 _("Toplam {count} video bulundu ve Ana Sayfaya rastgele dizildi!").format(count=total_videos)
             )


    def _on_search_triggered(self):
        """Arama kutusundaki metne göre (dosya adında, büyük/küçük harf
        duyarsız, kısmi eşleşme) aktif moddaki videoları filtreleyip
        YouTube tarzı bir liste olarak gösterir."""
        query = self.search_input.text().strip().lower()
        if not query:
            return

        candidates = self._filtered_videos_for_mode()
        matches = [
            v for v in candidates
            if query in os.path.basename(v.get('name', v.get('path', ''))).lower()
        ]

        MAX_RESULTS = 200
        truncated = len(matches) > MAX_RESULTS
        shown = matches[:MAX_RESULTS]

        # Eski satırları temizle (en sondaki stretch hariç)
        while self.search_results_layout.count() > 1:
            item = self.search_results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.search_results_thumb_rows = {}
        thread_pool = QThreadPool.globalInstance()
        for video_info in shown:
            vpath = video_info.get('path', '')
            path_hash = hashlib.md5(vpath.encode('utf-8')).hexdigest()
            thumb_path = os.path.join(self.THUMB_PATH, f"{path_hash}.jpg")

            row = SearchResultRow(video_info, thumb_path=thumb_path)
            row.clicked.connect(lambda p=vpath: self.stacked_widget.setCurrentIndex(1) if self.play_video(p) else None)
            self.search_results_thumb_rows[vpath] = row
            self.search_results_layout.insertWidget(self.search_results_layout.count() - 1, row)

            worker = ThumbnailWorker(vpath, thumb_path)
            worker.signals.finished.connect(self._on_search_thumb_ready)
            thread_pool.start(worker)

        count_text = f"{len(matches)} " + _("video bulundu")
        if truncated:
            count_text += " " + _("(ilk {max_res} tanesi gösteriliyor)").format(max_res=MAX_RESULTS)
        self.search_result_title_label.setText(f"{_('Arama')}: \"{query}\" ({count_text})")

        self.stacked_widget.setCurrentIndex(6)

    def _on_search_thumb_ready(self, video_path, thumb_path):
        if hasattr(self, 'search_results_thumb_rows') and video_path in self.search_results_thumb_rows:
            self.search_results_thumb_rows[video_path].set_thumbnail(thumb_path)

    def _on_folder_dump_requested(self, folder_path):
        """Seçilen klasörü (ve iç içe ne kadar derine giderse gitsin tüm alt
        klasörlerini) videolarla birlikte tek sayfaya döker."""
        folder_path = os.path.normpath(folder_path)

        def _is_under(video_path, folder):
            try:
                return os.path.commonpath([os.path.normpath(video_path), folder]) == folder
            except ValueError:
                return False  # Farklı sürücü/kök (Windows'ta olabilir), altında değildir

        # Sadece aktif moddaki videoları dök (Private içeriklerin Normal modda sızmasını engeller)
        active_videos = self._filtered_videos_for_mode()
        videos = [v for v in active_videos if _is_under(v.get('path', ''), folder_path)]

        folder_name = os.path.basename(folder_path) or folder_path
        if hasattr(self, 'folder_result_title_label'):
            self.folder_result_title_label.setText(f"{_('Klasör')}: {folder_name} ({len(videos)} " + _("video") + ")")
        if hasattr(self, 'folder_result_grid'):
            self.folder_result_grid.set_videos(videos, self.THUMB_PATH)

        self.stacked_widget.setCurrentIndex(5)

    def _theme_icon(self, theme_name, fallback_pixmap):
        """Önce sistemin aktif ikon temasından (freedesktop) ikon almayı
        dener; temada yoksa Qt'nin kendi yedek ikonuna düşer."""
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            icon = QApplication.instance().style().standardIcon(fallback_pixmap)
        return icon

    def _get_mode_root_dir(self, mode=None):
        """Verilen (veya mevcut) modun kök dizininin yolunu, ilgili
        Diskler-sayfası metin kutusundan okur."""
        mode = mode or self.current_mode
        field_map = {
            "Normal": "base_dirs_line_edit",
            "Adult": "adult_dirs_line_edit",
            "Dizi": "dizi_dirs_line_edit",
            "Sinema": "sinema_dirs_line_edit",
            "Kids": "kids_dirs_line_edit",
            "Korku": "korku_dirs_line_edit",
            "Müzik": "muzik_dirs_line_edit",
        }
        attr = field_map.get(mode)
        if attr and hasattr(self, attr):
            return getattr(self, attr).text().strip()
        return ""

    def _on_sidebar_video_clicked(self, path):
        """Sol paneldeki İzlenenler/Favoriler listesinden bir video seçilince oynatır."""
        if self.play_video(path):
            self.stacked_widget.setCurrentIndex(1)

    def _update_watched_and_favorites_lists(self):
        """İzlenenler ve Favoriler kutularını, aktif moddaki videolara göre tazeler."""
        videos = self._filtered_videos_for_mode()
        if hasattr(self, 'watched_list_box'):
            self.watched_list_box.set_videos([v for v in videos if v.get('watched')])
        if hasattr(self, 'favorites_list_box'):
            self.favorites_list_box.set_videos([v for v in videos if v.get('rating', 0) >= 1])

    def _update_mode_info_label(self):
        """Başlıktaki mod adı + o moddaki video sayısı bilgisini günceller."""
        mode_display_names = {
            "Normal": _("Normal Mod"),
            "Adult": _("Private Mod"),
            "Dizi": _("Dizi Mod"),
            "Sinema": _("Sinema Mod"),
            "Kids": _("Kids Mod"),
            "Korku": _("Korku Mod"),
            "Müzik": _("Müzik Mod")
        }
        if hasattr(self, 'mode_info_mode_label'):
            self.mode_info_mode_label.setText(mode_display_names.get(self.current_mode, self.current_mode))
        if hasattr(self, 'mode_info_count_label'):
            count = len(self._filtered_videos_for_mode())
            self.mode_info_count_label.setText(f"{count} " + _("video"))

    def _filtered_videos_for_mode(self, mode=None):
        """self.found_videos içinden, verilen (veya mevcut) moda ait videoları filtreler."""
        mode = mode or self.current_mode
        return [v for v in self.found_videos if v.get('mode', 'Normal') == mode]

    def _on_mode_changed(self, mode):
        """Settings menüsünden radyo ile bir mod seçildiğinde ana sayfayı ve
        önerilen videolar panelini sadece o moda ait videolarla günceller."""
        # Private (Adult) moda geçiş güvenliği
        if mode == "Adult":
            if not self.auth_manager.is_password_set():
                QMessageBox.warning(
                    self, _("Güvenlik Uyarısı"),
                    _("Private Mod için henüz parola belirlenmemiş!\n"
                      "Lütfen önce 'İndeksleme' menüsünden parola belirleyin.")
                )
                if hasattr(self, 'collapsible_menu'):
                    self.collapsible_menu.set_active_mode(self.current_mode)
                return

            dialog = VerifyPasswordDialog(self.auth_manager, self)
            if dialog.exec() != VerifyPasswordDialog.DialogCode.Accepted:
                # İptal edildi veya pencere kapatıldı: Eski modda kal
                if hasattr(self, 'collapsible_menu'):
                    self.collapsible_menu.set_active_mode(self.current_mode)
                return

        self.current_mode = mode
        filtered = self._filtered_videos_for_mode(mode)

        if hasattr(self, 'home_video_grid'):
            self.home_video_grid.set_videos(filtered, self.THUMB_PATH)
        self._update_recommended_videos()

        if hasattr(self, 'scan_results_label'):
            mode_names = {
                "Normal": _("Normal Mod"),
                "Adult": _("Private Mod"),
                "Dizi": _("Dizi Mod"),
                "Sinema": _("Sinema Mod"),
                "Kids": _("Kids Mod"),
                "Korku": _("Korku Mod"),
                "Müzik": _("Müzik Mod")
            }
            disp_mode = mode_names.get(mode, mode)
            self.scan_results_label.setText(
                _("Seçilen mod: {mode} ({count} video)").format(mode=disp_mode, count=len(filtered))
            )

        if hasattr(self, 'folder_explorer'):
            self.folder_explorer.set_root(self._get_mode_root_dir(mode))

        self._update_mode_info_label()
        self._update_watched_and_favorites_lists()

    # ------------------------------------
    # --- UI Oluşturma Metotları ---
    # ------------------------------------
    
    def _setup_mpv_widget(self):
        """MPV'nin yerleştirileceği AspectRatioWidget'ı oluşturur."""
        player_area = AspectRatioWidget(ratio=16/9)
        player_area.setStyleSheet("border: none; background-color: black;")
        self.mpv_area_widget = player_area.inner_content 
        self.mpv_area_widget.setStyleSheet("background-color: black; border: none;")
        return player_area

    def _show_seek_bar(self):
        if hasattr(self, 'seek_hide_timer'):
            self.seek_hide_timer.stop()
        if hasattr(self, 'seek_container'):
            self.seek_container.setVisible(True)
        if hasattr(self, 'volume_controls_widget'):
            self.volume_controls_widget.setVisible(True)
        if self.isFullScreen() and not getattr(self, '_fullscreen_bar_visible', False):
            self._fullscreen_bar_visible = True
            if hasattr(self, 'mpv_player_area'):
                self.mpv_player_area.apply_geometry()

    def _hide_seek_and_volume(self):
        if hasattr(self, 'seek_container'):
            self.seek_container.setVisible(False)
        if hasattr(self, 'volume_controls_widget'):
            self.volume_controls_widget.setVisible(False)
        if getattr(self, '_fullscreen_bar_visible', False):
            self._fullscreen_bar_visible = False
            if hasattr(self, 'mpv_player_area'):
                self.mpv_player_area.apply_geometry()

    def _schedule_hide_seek_bar(self):
        if hasattr(self, 'seek_slider') and self.seek_slider.isSliderDown():
            return
        if hasattr(self, 'seek_hide_timer') and not self.seek_hide_timer.isActive():
            self.seek_hide_timer.start(1000)

    def _check_mouse_hover_player(self):
        """MPV native penceresinin Qt mouse event'lerini yutmasını engelleyen global imleç kontrolü."""
        if not self._player_view_active or not hasattr(self, 'mpv_player_area'):
            return

        # Normal pencerede (tam ekranda DEĞİLKEN) seek çubuğu her zaman görünür kalsın;
        # fare çekilince alttaki kontrollerin yer değiştirmesini engeller.
        if not self.isFullScreen():
            self._show_seek_bar()
            return

        # Slider sürükleniyorsa gizleme
        if hasattr(self, 'seek_slider') and self.seek_slider.isSliderDown():
            self._show_seek_bar()
            return

        # Konum değil, HAREKET'e bakıyoruz — video üzerine yüzen kontrollerde
        # koordinat tabanlı algılama (native mpv penceresiyle çakıştığı için)
        # güvenilmez olabiliyor.
        from PyQt6.QtGui import QCursor
        current_pos = QCursor.pos()
        if current_pos != getattr(self, '_last_mouse_pos', None):
            self._last_mouse_pos = current_pos
            self._show_seek_bar()
            self._schedule_hide_seek_bar()  # hareket duraksarsa yine geri sayım başlasın

    # Bu metodun imzası değişti, artık player_area'yı dışarıdan alıyor.
    def _create_player_view(self, player_area): 
        player_view_container = QWidget()
        player_view_layout = QVBoxLayout(player_view_container)
        player_view_layout.setContentsMargins(10, 8, 10, 10)
        self.player_view_layout = player_view_layout
        player_view_layout.setSpacing(6)

        # 0. Video Başlığı (Fareyle seçilebilir ve kopyalanabilir)
        self.player_title_label = QLabel(_("Bir video seçiniz"))
        title_font = QFont("Arial", 13, QFont.Weight.Bold)
        self.player_title_label.setFont(title_font)
        self.player_title_label.setWordWrap(True)
        self.player_title_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.player_title_label.setContentsMargins(2, 2, 2, 4)
        player_view_layout.addWidget(self.player_title_label)
        
        # Kontrol butonları
        style = QApplication.instance().style()
        controls_bar = QHBoxLayout()
        controls_bar.setContentsMargins(10, 5, 10, 5)

        # --- Grup 1: Oynatma butonları (tam ekranda HER ZAMAN gizli) ---
        self.playback_controls_widget = QWidget()
        playback_layout = QHBoxLayout(self.playback_controls_widget)
        playback_layout.setContentsMargins(0, 0, 0, 0)
        playback_layout.setSpacing(6)

        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(self._theme_icon("media-skip-backward", QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.prev_btn.setIconSize(QSize(22, 22))
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.setProperty("is_player_control", True)
        self.prev_btn.setToolTip(_("Önceki Video"))
        self.prev_btn.setEnabled(False)  # Başlangıçta geçmiş boş olduğu için pasif
        self.prev_btn.clicked.connect(self._play_prev_video)
        playback_layout.addWidget(self.prev_btn)

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(self._theme_icon("media-playback-start", QStyle.StandardPixmap.SP_MediaPlay)) 
        self.play_pause_btn.setIconSize(QSize(22, 22)) 
        self.play_pause_btn.setFixedSize(40, 40) 
        self.play_pause_btn.setProperty("is_player_control", True)
        self.play_pause_btn.setToolTip(_("Oynat / Duraklat"))
        self.play_pause_btn.clicked.connect(self._toggle_pause) 
        playback_layout.addWidget(self.play_pause_btn)
        
        next_btn = QPushButton()
        next_btn.setIcon(self._theme_icon("media-skip-forward", QStyle.StandardPixmap.SP_MediaSkipForward))
        next_btn.setIconSize(QSize(22, 22)) 
        next_btn.setFixedSize(40, 40) 
        next_btn.setProperty("is_player_control", True)
        next_btn.setToolTip(_("Sonraki Rastgele Video"))
        next_btn.clicked.connect(self._play_next_video)
        playback_layout.addWidget(next_btn)

        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setIcon(self._theme_icon("view-fullscreen", QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.fullscreen_btn.setIconSize(QSize(22, 22))
        self.fullscreen_btn.setFixedSize(40, 40) 
        self.fullscreen_btn.setProperty("is_player_control", True)
        self.fullscreen_btn.setToolTip(_("Tam Ekran"))
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen) 
        playback_layout.addWidget(self.fullscreen_btn)
        
        menu_btn = QPushButton()
        menu_btn.setIcon(self._theme_icon("folder-open", QStyle.StandardPixmap.SP_DirIcon))
        menu_btn.setIconSize(QSize(22, 22))
        menu_btn.setFixedSize(40, 40)
        menu_btn.setProperty("is_player_control", True)
        menu_btn.setToolTip(_("Videonun bulunduğu klasörü aç"))
        menu_btn.clicked.connect(self._open_video_folder)
        playback_layout.addWidget(menu_btn)

        controls_bar.addWidget(self.playback_controls_widget)
        controls_bar.addStretch(1)

        # --- Grup 2: Hız seçici (tam ekranda HER ZAMAN gizli) ---
        self.speed_controls_widget = QWidget()
        speed_layout = QHBoxLayout(self.speed_controls_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.addWidget(QLabel(_("Hız:")))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.50x", "0.75x", "1.00x", "1.25x", "1.50x", "1.75x", "2.00x"])
        self.speed_combo.setCurrentText("1.00x")
        self.speed_combo.setFixedHeight(30)
        self.speed_combo.currentTextChanged.connect(self._on_speed_combo_changed)
        speed_layout.addWidget(self.speed_combo)
        controls_bar.addWidget(self.speed_controls_widget)

        # --- Grup 3: Ses kontrolleri (tam ekranda seek çubuğuyla BİRLİKTE, fareyle görünür/gizli) ---
        self.volume_controls_widget = QWidget()
        volume_layout = QHBoxLayout(self.volume_controls_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)

        self.mute_btn = QPushButton()
        self.mute_btn.setIcon(self._theme_icon("audio-volume-high", QStyle.StandardPixmap.SP_MediaVolume))
        self.mute_btn.setIconSize(QSize(20, 20))
        self.mute_btn.setFixedSize(40, 40)
        self.mute_btn.setProperty("is_player_control", True)
        self.mute_btn.setToolTip(_("Sesi Aç / Kapat"))
        self.mute_btn.clicked.connect(self._toggle_mute)
        volume_layout.addWidget(self.mute_btn)

        volume_layout.addWidget(QLabel(_("Ses:")))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setSingleStep(2)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(self._set_player_volume) 
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("%100")
        self.volume_label.setFixedWidth(40)
        volume_layout.addWidget(self.volume_label)

        # (Ses kontrolleri artık seek çubuğuyla aynı satırda — yukarı taşındı)

        # 1. Video alanını ekle (Gereksiz boşluk bırakmayacak şekilde esnemesiz)
        player_view_layout.addWidget(player_area)

        # 2. Seek Bar ve Süre Göstergesi Konteyneri (Video altına kilitli)
        self.seek_container = QFrame()
        self.seek_container.setFixedHeight(38)
        self.seek_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        seek_box_layout = QHBoxLayout(self.seek_container)
        seek_box_layout.setContentsMargins(8, 2, 8, 2)
        seek_box_layout.setSpacing(10)

        self.seek_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName('seek_slider')
        self.seek_slider.setRange(0, 100)
        self.seek_slider.setValue(0)
        self.seek_slider.setSingleStep(1)
        self.seek_slider.setStyleSheet(
            "QSlider { background: transparent; } "
            "QSlider::groove:horizontal { background: rgba(140, 140, 140, 0.4); height: 6px; border-radius: 3px; } "
            "QSlider::sub-page:horizontal { background: #007acc; border-radius: 3px; } "
            "QSlider::handle:horizontal { background: #007acc; border: 1.5px solid #ffffff; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }"
        )

        self.seek_time_label = QLabel("00:00 / 00:00")
        self.seek_time_label.setObjectName('seek_time_label')
        self.seek_time_label.setStyleSheet("background-color: palette(base); color: palette(text); padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        self.seek_time_label.setFixedHeight(22)
        self.seek_time_label.setMinimumWidth(90)
        self.seek_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        seek_box_layout.addWidget(self.seek_slider, 1)
        seek_box_layout.addWidget(self.seek_time_label)
        seek_box_layout.addWidget(self.volume_controls_widget)

        player_view_layout.addWidget(self.seek_container)

        # 1 saniyelik otomatik gizlenme zamanlayıcısı
        self.seek_hide_timer = QTimer(self)
        self.seek_hide_timer.setSingleShot(True)
        self.seek_hide_timer.setInterval(1000)
        self.seek_hide_timer.timeout.connect(self._hide_seek_and_volume)

        # MPV alanını da kapsayan imleç takip zamanlayıcısı
        self.hover_poll_timer = QTimer(self)
        self.hover_poll_timer.setInterval(150)
        self.hover_poll_timer.timeout.connect(self._check_mouse_hover_player)

        # Seek bağlantıları
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)

        # 3. Kontrol Butonları
        player_view_layout.addLayout(controls_bar)

        self.rating_row_widget = QWidget()
        rating_row = QHBoxLayout(self.rating_row_widget)
        rating_row.setContentsMargins(0, 4, 0, 4)
        self.watched_checkbox = QCheckBox(_("İzlendi"))
        self.watched_checkbox.stateChanged.connect(self._on_watched_changed)
        rating_row.addWidget(self.watched_checkbox)
        rating_row.addSpacing(20)
        rating_row.addWidget(QLabel(_("Puan:")))
        self.rating_widget = StarRatingWidget(max_stars=7)
        self.rating_widget.rating_changed.connect(self._on_rating_changed)
        rating_row.addWidget(self.rating_widget)
        rating_row.addSpacing(25)
        self.autoplay_checkbox = QCheckBox(_("Sıradaki Videoyu Otomatik Oynat"))
        self.autoplay_checkbox.setChecked(True)
        self.autoplay_checkbox.toggled.connect(self._on_autoplay_toggled)
        rating_row.addWidget(self.autoplay_checkbox)
        rating_row.addStretch(1)
        player_view_layout.addWidget(self.rating_row_widget)
        
        # 4. Canlı Yorum / Özet / Notlar Alanı
        self.comment_placeholder_container = QWidget()
        description_container = QVBoxLayout(self.comment_placeholder_container)
        description_container.setContentsMargins(0, 2, 0, 0)
        description_container.setSpacing(4)

        desc_header_layout = QHBoxLayout()
        desc_label = QLabel(_("Video Özeti & Kişisel Notlar:"))
        desc_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        desc_header_layout.addWidget(desc_label)
        desc_header_layout.addStretch(1)
        description_container.addLayout(desc_header_layout)

        self.video_notes_edit = QTextEdit()
        self.video_notes_edit.setPlaceholderText(_("Bu video için özet veya kişisel notlarınızı buraya yazabilirsiniz (yazdıklarınız otomatik kaydedilir)..."))
        self.video_notes_edit.setFixedHeight(60)
        self.video_notes_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.video_notes_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_notes_edit.textChanged.connect(self._on_video_notes_changed)
        description_container.addWidget(self.video_notes_edit)

        player_view_layout.addWidget(self.comment_placeholder_container)

        # 5. Tüm bileşenleri yukarı yaslayıp alttaki boşlukları yok et
        player_view_layout.addStretch(1)

        # Oynatıcı kontrol butonlarının hiçbiri klavye odağını çalmasın —
        # aksi halde örneğin tam ekran butonuna tıkladıktan sonra Boşluk
        # tuşu pause/play yerine o butonu yeniden tetikliyordu.
        for btn in player_view_container.findChildren(QPushButton):
            if btn.property("is_player_control"):
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        return player_view_container

    def resizeEvent(self, event):
        super().resizeEvent(event)

    
    def _setup_config_files(self):
        if not os.path.exists(self.CONFIG_PATH):
            os.makedirs(self.CONFIG_PATH, exist_ok=True)

        self.settings_file = os.path.join(self.CONFIG_PATH, "settings.json")
        self.index_file = os.path.join(self.CONFIG_PATH, "index_data.json")

        for fpath, default_content in [(self.settings_file, "{}"), (self.index_file, "[]")]:
            if not os.path.exists(fpath):
                try:
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(default_content)
                except Exception as e:
                    print(f"Hata: {fpath} dosyası oluşturulamadı: {e}")

    def _save_persistent_data(self):
        """Dizin ayarlarını ve indekslenen videoları diske kaydeder."""
        settings = {
            "base_dir": self.base_dirs_line_edit.text().strip() if hasattr(self, 'base_dirs_line_edit') else "",
            "adult_dir": self.adult_dirs_line_edit.text().strip() if hasattr(self, 'adult_dirs_line_edit') else "",
            "dizi_dir": self.dizi_dirs_line_edit.text().strip() if hasattr(self, 'dizi_dirs_line_edit') else "",
            "sinema_dir": self.sinema_dirs_line_edit.text().strip() if hasattr(self, 'sinema_dirs_line_edit') else "",
            "kids_dir": self.kids_dirs_line_edit.text().strip() if hasattr(self, 'kids_dirs_line_edit') else "",
            "korku_dir": self.korku_dirs_line_edit.text().strip() if hasattr(self, 'korku_dirs_line_edit') else "",
            "muzik_dir": self.muzik_dirs_line_edit.text().strip() if hasattr(self, 'muzik_dirs_line_edit') else "",
            "autoplay": self.autoplay_checkbox.isChecked() if hasattr(self, 'autoplay_checkbox') else True,
            "language": getattr(self, 'current_language', 'en'),
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.found_videos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Kayıt hatası: {e}")

    def _on_language_changed_from_ui(self, lang_code):
        """Ayarlar sayfasından yeni dil seçildiğinde tetiklenir."""
        if self.current_language != lang_code:
            self.current_language = lang_code
            self._save_persistent_data()
            QMessageBox.information(
                self,
                _("Dil Değiştirildi"),
                _("Dil ayarının geçerli olabilmesi için lütfen uygulamayı kapatıp yeniden başlatın.")
            )

    def _handle_backup(self, target_path):
        """Ayarları ve video indeksini tek bir JSON yedeğinde toplar."""
        try:
            settings_data = {}
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
            backup_data = {
                "version": "1.0",
                "settings": settings_data,
                "found_videos": self.found_videos
            }
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Başarılı", f"Yedek başarıyla oluşturuldu:\n{target_path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Yedekleme başarısız oldu:\n{e}")

    def _handle_restore(self, source_path):
        """Yedek dosyasından ayarları ve indeksi geri yükler."""
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            if "settings" in backup_data and "found_videos" in backup_data:
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data["settings"], f, ensure_ascii=False, indent=2)
                with open(self.index_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data["found_videos"], f, ensure_ascii=False, indent=2)
                self._load_persistent_data()
                QMessageBox.information(self, "Başarılı", "Yedek başarıyla geri yüklendi ve uygulandı!")
            else:
                QMessageBox.warning(self, "Geçersiz Dosya", "Seçilen dosya geçerli bir ThisIsMyTube yedeği değil.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Geri yükleme başarısız oldu:\n{e}")

    def _handle_clear_cache(self):
        """Küçük resim (thumbnail) önbelleğini temizler."""
        try:
            count = 0
            if os.path.exists(self.THUMB_PATH):
                for fname in os.listdir(self.THUMB_PATH):
                    fpath = os.path.join(self.THUMB_PATH, fname)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        count += 1
            QMessageBox.information(self, "Tamamlandı", f"Önbellek temizlendi. Toplam {count} küçük resim silindi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Önbellek temizleme sırasında hata oluştu:\n{e}")

    def _handle_reset(self):
        """Tüm ayarları ve verileri sıfırlar."""
        try:
            self.found_videos = []
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    f.write("{}")
            if os.path.exists(self.index_file):
                with open(self.index_file, 'w', encoding='utf-8') as f:
                    f.write("[]")
            if hasattr(self, 'auth_manager'):
                self.auth_manager.remove_password()
            
            # Form alanlarını temizle
            for field in ['base_dirs_line_edit', 'adult_dirs_line_edit', 'dizi_dirs_line_edit',
                          'sinema_dirs_line_edit', 'kids_dirs_line_edit', 'korku_dirs_line_edit', 'muzik_dirs_line_edit']:
                if hasattr(self, field):
                    getattr(self, field).clear()

            # Otomatik oynatmayı fabrika varsayılanına (Açık) döndür
            if hasattr(self, 'autoplay_checkbox'):
                self.autoplay_checkbox.blockSignals(True)
                self.autoplay_checkbox.setChecked(True)
                self.autoplay_checkbox.blockSignals(False)

            self._on_mode_changed("Normal")
            QMessageBox.information(self, "Sıfırlandı", "Tüm ayarlar ve indeks sıfırlandı. Fabrika ayarlarına dönüldü.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Sıfırlama sırasında hata oluştu:\n{e}")

    def _load_persistent_data(self):
        """Program açılışında kayıtlı dizinleri ve videoları yükler."""
        if not hasattr(self, 'settings_file'):
            self._setup_config_files()

        # 1. Dizin ayarlarını yükle
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                if hasattr(self, 'base_dirs_line_edit') and settings.get("base_dir"):
                    self.base_dirs_line_edit.setText(settings["base_dir"])
                if hasattr(self, 'adult_dirs_line_edit') and settings.get("adult_dir"):
                    self.adult_dirs_line_edit.setText(settings["adult_dir"])
                if hasattr(self, 'dizi_dirs_line_edit') and settings.get("dizi_dir"):
                    self.dizi_dirs_line_edit.setText(settings["dizi_dir"])
                if hasattr(self, 'sinema_dirs_line_edit') and settings.get("sinema_dir"):
                    self.sinema_dirs_line_edit.setText(settings["sinema_dir"])
                if hasattr(self, 'kids_dirs_line_edit') and settings.get("kids_dir"):
                    self.kids_dirs_line_edit.setText(settings["kids_dir"])
                if hasattr(self, 'korku_dirs_line_edit') and settings.get("korku_dir"):
                    self.korku_dirs_line_edit.setText(settings["korku_dir"])
                if hasattr(self, 'muzik_dirs_line_edit') and settings.get("muzik_dir"):
                    self.muzik_dirs_line_edit.setText(settings["muzik_dir"])
                if hasattr(self, 'autoplay_checkbox') and "autoplay" in settings:
                    self.autoplay_checkbox.blockSignals(True)
                    self.autoplay_checkbox.setChecked(bool(settings["autoplay"]))
                    self.autoplay_checkbox.blockSignals(False)
                if "language" in settings:
                    self.current_language = settings.get("language", "en")
                    if hasattr(self, 'settings_view') and hasattr(self.settings_view, 'set_current_language'):
                        self.settings_view.set_current_language(self.current_language)
            except Exception as e:
                print(f"Ayar yükleme hatası: {e}")

        if hasattr(self, 'folder_explorer'):
            self.folder_explorer.set_root(self._get_mode_root_dir())

        # 2. İndekslenmiş videoları DOĞRUDAN yükle — artık her dosyanın hâlâ
        # var olup olmadığını burada kontrol ETMİYORUZ. Bu kontrol artık
        # sadece bir video gerçekten oynatılmaya çalışıldığında yapılıyor
        # (play_video içinde) — silinmiş/taşınmış dosyalar yüzünden açılışta
        # binlerce gereksiz disk sorgusu yapmaktan kaçınıyoruz. Kartların
        # kendisi (`set_videos`) zaten aşamalı/async oluşturulduğu için o
        # kısımdaki ilerleme çubuğu aynen kalıyor.
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.found_videos = json.load(f) or []
            except Exception as e:
                print(f"İndeks yükleme hatası: {e}")
                self.found_videos = []
        else:
            self.found_videos = []

        print(f"[{len(self.found_videos)} video indeksten okundu]")
        if hasattr(self, 'scan_results_label'):
            self.scan_results_label.setText(
                _("Kayıtlı indeks yüklendi: Toplam {count} video.").format(count=len(self.found_videos))
            )

        if hasattr(self, 'home_video_grid'):
            self.home_video_grid.set_videos(self._filtered_videos_for_mode(), self.THUMB_PATH)
            self._update_recommended_videos()

        self._update_mode_info_label()
        self._update_watched_and_favorites_lists()

    def _set_app_icon(self):
        icon_filename = "ThisisMyTube.png"
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_filename)
        system_path = os.path.join("/usr/share/thisismytube", icon_filename)

        if os.path.exists(local_path):
            self.icon_path = local_path
        elif os.path.exists(system_path):
            self.icon_path = system_path
        
        if self.icon_path:
            self.setWindowIcon(QIcon(self.icon_path))

    def _update_menu_style(self):
        for btn in self.findChildren(QPushButton):
            if btn.property("is_menu_item"):
                if btn.property("menu_id") == self.active_menu_id:
                    btn.setStyleSheet("QPushButton { text-align: left; padding: 5px 10px; border: none; background-color: palette(midlight); border-left: 3px solid palette(highlight); } QPushButton:hover { background-color: palette(midlight); }")
                else:
                    btn.setStyleSheet("QPushButton { text-align: left; padding: 5px 10px; border: none; background-color: transparent; border-left: 3px solid transparent; }")

    def _go_home(self):
        """Logoya tıklanınca Ana Sayfa'ya döner, sol menüdeki vurguyu da günceller."""
        self.active_menu_id = "home"
        self._update_menu_style()
        self.stacked_widget.setCurrentIndex(0)

    def _on_menu_item_clicked(self):
        sender = self.sender()
        menu_id = sender.property("menu_id")
        page_index = sender.property("page_index")
        
        if menu_id:
            self.active_menu_id = menu_id
            self._update_menu_style()
        if page_index is not None:
            self.stacked_widget.setCurrentIndex(page_index)

    def _create_header(self):
        header_frame = QFrame()
        header_frame.setObjectName("header_frame") 
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        logo_label = ClickableLabel()
        logo_label.setObjectName("logo_label") 
        logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
        logo_label.setToolTip(_("Ana Sayfaya dön"))
        logo_size = 86 
        if self.icon_path:
            pixmap = QPixmap(self.icon_path).scaledToHeight(logo_size, Qt.TransformationMode.FastTransformation) 
            logo_label.setPixmap(pixmap)
            logo_label.setFixedSize(logo_size, logo_size)
        else:
            logo_label.setText("#logo")
            logo_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        logo_label.clicked.connect(self._go_home)
        
        header_layout.addWidget(logo_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_("Video arama (birkaç harf yazıp Enter'a basın)"))
        self.search_input.setFixedHeight(40)
        self.search_input.setMaximumWidth(420)
        self.search_input.returnPressed.connect(self._on_search_triggered)
        header_layout.addWidget(self.search_input, 1)
        
        search_button = QPushButton()
        search_button.setIcon(self._theme_icon("edit-find", QStyle.StandardPixmap.SP_FileDialogContentsView))
        search_button.setIconSize(QSize(18, 18))
        search_button.setFixedSize(40, 40)
        search_button.clicked.connect(self._on_search_triggered)
        header_layout.addWidget(search_button)

        header_layout.addStretch(1)

        self.mode_info_widget = QWidget()
        self.mode_info_widget.setMinimumWidth(140)
        mode_info_layout = QVBoxLayout(self.mode_info_widget)
        mode_info_layout.setContentsMargins(0, 0, 0, 0)
        mode_info_layout.setSpacing(0)

        self.mode_info_mode_label = QLabel(self.current_mode)
        self.mode_info_mode_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mode_info_mode_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        mode_info_layout.addWidget(self.mode_info_mode_label)

        self.mode_info_count_label = QLabel("0 video")
        self.mode_info_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mode_info_count_label.setStyleSheet("color: #999999; font-size: 9pt;")
        mode_info_layout.addWidget(self.mode_info_count_label)

        header_layout.addWidget(self.mode_info_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return header_frame

    def _create_settings_menu(self):
        settings_menu = QFrame()
        settings_menu.setObjectName("settings_menu") 
        settings_menu.setMinimumWidth(220)
        settings_menu.setMaximumWidth(270)
        
        settings_menu_layout = QVBoxLayout(settings_menu)
        settings_menu_layout.setContentsMargins(0, 10, 0, 10) 
        settings_menu_layout.setSpacing(1) 
        
        settings_label = QLabel(_("\u2699\ufe0f Ayarlar & Seçenekler"))
        settings_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        settings_label.setContentsMargins(10, 5, 10, 5)
        settings_menu_layout.addWidget(settings_label)
        
        # (theme_icon, fallback, display_text, menu_id, page_index)
        option_buttons_data = [
            ("go-home", QStyle.StandardPixmap.SP_DirHomeIcon, _("Ana Sayfa"), "home", 0),
            ("drive-harddisk", QStyle.StandardPixmap.SP_DriveHDIcon, _("İndeksleme"), "scan", 2),
            ("preferences-system", QStyle.StandardPixmap.SP_FileDialogDetailedView, _("Ayarlar"), "settings", 3),
            ("help-about", QStyle.StandardPixmap.SP_MessageBoxInformation, _("Hakkında"), "about", 4),
        ]

        for theme_name, fallback_pixmap, text, menu_id, page_idx in option_buttons_data:
            btn = QPushButton(f" {text}") 
            btn.setIcon(self._theme_icon(theme_name, fallback_pixmap))
            btn.setIconSize(QSize(18, 18))
            btn.setProperty("is_menu_item", True) 
            btn.setProperty("menu_id", menu_id)
            btn.setProperty("page_index", page_idx)
            btn.setFixedHeight(35)
            btn.clicked.connect(self._on_menu_item_clicked)
            settings_menu_layout.addWidget(btn)
        
        settings_menu_layout.addSpacing(10)

        self.collapsible_menu = CollapsibleModeMenu()
        self.collapsible_menu.mode_changed.connect(self._on_mode_changed)
        settings_menu_layout.addWidget(self.collapsible_menu)

        # "Klasörler"den itibaren olan bölüm, mod menüsüne dokunmadan kendi
        # kaydırma çubuğuna sahip ayrı bir alana sarılıyor.
        lower_panel_content = QWidget()
        lower_panel_layout = QVBoxLayout(lower_panel_content)
        lower_panel_layout.setContentsMargins(0, 0, 0, 0)
        lower_panel_layout.setSpacing(6)

        self.folder_explorer = FolderExplorerBox()
        self.folder_explorer.dump_requested.connect(self._on_folder_dump_requested)
        lower_panel_layout.addWidget(self.folder_explorer)

        self.watched_list_box = SimpleVideoListBox(_("\u2705 İzlenenler"))
        self.watched_list_box.video_clicked.connect(self._on_sidebar_video_clicked)
        lower_panel_layout.addWidget(self.watched_list_box)

        self.favorites_list_box = SimpleVideoListBox(_("\u2b50 Favoriler"))
        self.favorites_list_box.video_clicked.connect(self._on_sidebar_video_clicked)
        lower_panel_layout.addWidget(self.favorites_list_box)

        lower_panel_layout.addStretch(1)

        lower_panel_scroll = QScrollArea()
        lower_panel_scroll.setWidgetResizable(True)
        lower_panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        lower_panel_scroll.setWidget(lower_panel_content)
        settings_menu_layout.addWidget(lower_panel_scroll, 1) 

        return settings_menu

    def _create_home_view(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.home_video_grid = ResponsiveVideoGrid(self) 
        scroll_area.setWidget(self.home_video_grid)

        # Kullanıcı sayfanın sonuna yaklaştığında sıradaki kartları otomatik ekle
        def _check_scroll_bottom(value):
            max_val = scroll_area.verticalScrollBar().maximum()
            if max_val > 0 and value >= max_val - 350:
                self.home_video_grid.load_more(count=40)

        scroll_area.verticalScrollBar().valueChanged.connect(_check_scroll_bottom)
        return scroll_area
    
    def _create_folder_result_view(self):
        """'Dök' butonuyla seçilen bir klasörün (ve tüm alt klasörlerinin)
        videolarını gösteren, her seferinde yeniden doldurulan tek sayfa."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 15, 15, 15)

        self.folder_result_title_label = QLabel(_("Klasör İçeriği"))
        self.folder_result_title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(self.folder_result_title_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.folder_result_grid = ResponsiveVideoGrid(self)
        scroll_area.setWidget(self.folder_result_grid)
        layout.addWidget(scroll_area)

        return container

    def _create_search_result_view(self):
        """Arama sonuçlarını YouTube tarzı, dikey liste (solda resim, sağda
        başlık) şeklinde gösteren, her aramada yeniden doldurulan tek sayfa."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.search_result_title_label = QLabel(_("Arama Sonuçları"))
        self.search_result_title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(self.search_result_title_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        results_widget = QWidget()
        self.search_results_layout = QVBoxLayout(results_widget)
        self.search_results_layout.setSpacing(6)
        self.search_results_layout.addStretch(1)
        scroll_area.setWidget(results_widget)
        layout.addWidget(scroll_area)

        return container

    def _create_disk_scan_settings_view(self):
        # Sayfanın kaydırılabilir olması için bir ScrollArea içine alıyoruz
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        disk_settings_widget = QWidget()
        layout = QVBoxLayout(disk_settings_widget)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(12)

        title = QLabel(_("Disk Tarama Ayarları"))
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Dizin tanımları listesi: (Label, attr_name, placeholder)
        dir_fields = [
            (_("<b>Taranacak Ana Dizin:</b>"), "base_dirs_line_edit", _("/home/kullanici/Videolar veya /mnt/HariciDisk")),
            (_("<b>Private İçerik Dizini:</b>"), "adult_dirs_line_edit", _("/home/kullanici/Videolar/Private")),
            (_("<b>Dizi İçerik Dizini:</b>"), "dizi_dirs_line_edit", _("/home/kullanici/Videolar/Diziler")),
            (_("<b>Sinema İçerik Dizini:</b>"), "sinema_dirs_line_edit", _("/home/kullanici/Videolar/Filmler")),
            (_("<b>Kids İçerik Dizini:</b>"), "kids_dirs_line_edit", _("/home/kullanici/Videolar/CizgiFilmler")),
            (_("<b>Korku İçerik Dizini:</b>"), "korku_dirs_line_edit", _("/home/kullanici/Videolar/Korku")),
            (_("<b>Müzik İçerik Dizini:</b>"), "muzik_dirs_line_edit", _("/home/kullanici/Videolar/Muzik")),
        ]

        for label_text, attr_name, placeholder in dir_fields:
            layout.addWidget(QLabel(label_text))
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(placeholder)
            line_edit.setFixedHeight(36)
            setattr(self, attr_name, line_edit)
            row_layout.addWidget(line_edit, 1)
            
            btn = QPushButton(_("Dizin Ekle"))
            btn.setFixedHeight(36)
            btn.setFixedWidth(110)
            btn.clicked.connect(lambda checked, le=line_edit: self._add_directory_button_clicked(le))
            row_layout.addWidget(btn)
            
            layout.addLayout(row_layout)

            # Sadece Private dizini satırının altına kırmızı Parola butonu
            if attr_name == "adult_dirs_line_edit":
                pwd_row = QHBoxLayout()
                pwd_row.setContentsMargins(0, 0, 0, 2)
                self.pwd_btn = QPushButton(_("Parola"))
                self.pwd_btn.setFixedHeight(28)
                self.pwd_btn.setFixedWidth(90)
                self.pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.pwd_btn.setStyleSheet(
                    "background-color: #c9302c; color: #ffffff; font-weight: bold; border-radius: 4px; border: 1px solid #ac2925;"
                )
                self.pwd_btn.clicked.connect(self._open_password_dialog)
                pwd_row.addWidget(self.pwd_btn)
                pwd_row.addStretch(1)
                layout.addLayout(pwd_row)

        layout.addSpacing(10)

        scan_button = QPushButton(_("Taramayı Başlat"))
        scan_button.setDefault(True)
        scan_button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        scan_button.setFixedHeight(44)
        scan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_button.setStyleSheet(
            "QPushButton {"
            "   background-color: #007acc;"
            "   color: #ffffff;"
            "   border: 2px solid #3399ff;"
            "   border-radius: 6px;"
            "   padding: 6px 14px;"
            "}"
            "QPushButton:hover {"
            "   background-color: #008be5;"
            "   border: 2px solid #66b2ff;"
            "}"
            "QPushButton:pressed {"
            "   background-color: #005c99;"
            "   border: 2px solid #005c99;"
            "}"
        )
        glow = QGraphicsDropShadowEffect(scan_button)
        glow.setColor(QColor(0, 150, 255, 180))
        glow.setOffset(0, 0)
        glow.setBlurRadius(16)
        scan_button.setGraphicsEffect(glow)
        scan_button.clicked.connect(self._start_disk_scan) 
        layout.addWidget(scan_button)

        self.scan_results_label = QLabel(_("Tarama yapılmadı. Video listesi boş."))
        self.scan_results_label.setStyleSheet("padding: 8px; border-radius: 4px;")
        layout.addWidget(self.scan_results_label)

        layout.addStretch(1) 
        scroll_area.setWidget(disk_settings_widget)
        return scroll_area
        
    def _create_about_view(self):
        """Uygulama künyesini, logosunu, teknik detayları ve telif hakkı
        bilgilerini içeren Hakkında sayfası."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.setSpacing(16)

        title = QLabel(_("ThisIsMyTube Hakkında"))
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        # Logo alanı (Varsa uygulama logosu, yoksa şık metin gösterimi)
        logo_label = QLabel()
        if getattr(self, 'icon_path', None) and os.path.exists(self.icon_path):
            pixmap = QPixmap(self.icon_path).scaledToHeight(96, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("[ ThisIsMyTube ]")
            logo_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        layout.addWidget(logo_label)

        # Teknik Bilgiler ve Bağlantılar (HTML formatında, tıklanabilir link ile)
        meta_info = QLabel(
            f"<table style='font-size: 13px; line-height: 1.6; border-collapse: collapse;'>"
            f"<tr><td><b>{_('Sürüm:')}</b></td><td style='padding-left: 12px;'>1.0.0</td></tr>"
            f"<tr><td><b>{_('Lisans:')}</b></td><td style='padding-left: 12px;'>GNU GPLv3</td></tr>"
            f"<tr><td><b>{_('GUI / UX:')}</b></td><td style='padding-left: 12px;'>Qt-6</td></tr>"
            f"<tr><td><b>{_('Programlama Dili:')}</b></td><td style='padding-left: 12px;'>Python3</td></tr>"
            f"<tr><td><b>{_('Yapımcı:')}</b></td><td style='padding-left: 12px;'>A. Serhat KILIÇOĞLU (shampuan)</td></tr>"
            f"<tr><td><b>GitHub:</b></td><td style='padding-left: 12px;'>"
            f"<a href='https://github.com/shampuan' style='color: #007acc; text-decoration: none;'>www.github.com/shampuan</a>"
            f"</td></tr>"
            f"</table>"
        )
        meta_info.setTextFormat(Qt.TextFormat.RichText)
        meta_info.setOpenExternalLinks(True)
        meta_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(meta_info)

        # Ayrıcı Çizgi
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: palette(mid);")
        layout.addWidget(separator)

        # Geliştirilmiş Tanıtım Açıklaması
        description = QLabel(
            _("Bu program; bilgisayarınızda depolanan video, film, dizi ve müzik gibi tüm yerel "
              "medya arşivinizi modern bir video platformu deneyimiyle önünüze seren gelişmiş bir "
              "kişisel medya merkezidir. Popüler video servislerinin sunduğu gezinme konforu, "
              "öneri akışı ve izleme kolaylıklarını tamamen çevrimdışı, gizlilik odaklı ve "
              "hızlı bir ortamda sunarak eğlenceli bir izleme deneyimi sağlar.")
        )
        description.setFont(QFont("Arial", 11))
        description.setWordWrap(True)
        description.setStyleSheet("line-height: 1.4;")
        layout.addWidget(description)

        # Garanti Reddi
        disclaimer = QLabel(_("Bu program hiçbir garanti getirmez."))
        disclaimer.setFont(QFont("Arial", 10))
        disclaimer.setStyleSheet("color: palette(text); font-style: italic;")
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        # Telif Hakkı Bildirimi
        copyright_label = QLabel(_("Telif hakkı {copy} 2026 - A. Serhat KILIÇOĞLU").format(copy=chr(169)))
        copyright_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        copyright_label.setStyleSheet("color: palette(text);")
        layout.addWidget(copyright_label)

        layout.addStretch(1)
        scroll_area.setWidget(container)
        return scroll_area

    def _add_directory_button_clicked(self, line_edit):
        """Dizin seçimi iletişim kutusunu açar ve sonucu QLineEdit adres çubuğuna yazar."""
        directory = QFileDialog.getExistingDirectory(self, _("Dizin Seçin"))
        if directory:
            line_edit.setText(directory)

    def _open_password_dialog(self):
        """Parola belirleme/değiştirme penceresini açar."""
        dialog = SetPasswordDialog(self.auth_manager, self)
        dialog.exec()

    
    def _create_sidebar(self, num_items=50):
        self.sidebar_scroll_area = QScrollArea()
        self.sidebar_scroll_area.setWidgetResizable(True)
        self.sidebar_scroll_area.setMinimumWidth(280)

        self.sidebar_content_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_content_widget)
        self.sidebar_layout.setContentsMargins(8, 10, 8, 10)
        self.sidebar_layout.setSpacing(8)

        sidebar_title = QLabel(_("> Önerilen Videolar"))
        sidebar_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        sidebar_title.setContentsMargins(4, 0, 0, 4)
        self.sidebar_layout.addWidget(sidebar_title)

        self.sidebar_cards_by_path = {}
        self.sidebar_layout.addStretch(1)

        self.sidebar_scroll_area.setWidget(self.sidebar_content_widget)
        return self.sidebar_scroll_area

    def _update_recommended_videos(self, limit=50):
        """Mevcut videolardan rastgele seçim yaparak yan paneli kartlarla doldurur."""
        if not hasattr(self, 'sidebar_layout'):
            return

        # Eski kartları temizle (başlık etiketi VE sondaki stretch hariç —
        # ikisi de sabit kalmalı, bu yüzden sınır 2, 1 değil)
        while self.sidebar_layout.count() > 2:
            item = self.sidebar_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        self.sidebar_cards_by_path.clear()

        # Liste boşsa (örn. sıfırlama yapıldıysa) temizliği yapıp çık
        if not self.found_videos:
            return

        thread_pool = QThreadPool.globalInstance()

        # Rastgele videolar seç (sadece aktif moddaki videolardan)
        shuffled = self._filtered_videos_for_mode()
        random.shuffle(shuffled)
        selected_videos = shuffled[:limit]

        for video_info in selected_videos:
            vpath = video_info.get('path', '')
            path_hash = hashlib.md5(vpath.encode('utf-8')).hexdigest()
            thumb_path = os.path.join(self.THUMB_PATH, f"{path_hash}.jpg")

            card = RecommendedVideoCard(video_info, thumb_path=thumb_path, parent=self.sidebar_content_widget)
            card.clicked.connect(lambda p=vpath: self.stacked_widget.setCurrentIndex(1) if self.play_video(p) else None)
            self.sidebar_cards_by_path[vpath] = card

            # Başlıktan hemen sonra, en alttaki esnek boşluğun üstüne yerleştir
            self.sidebar_layout.insertWidget(self.sidebar_layout.count() - 1, card)

            if not os.path.exists(thumb_path):
                worker = ThumbnailWorker(vpath, thumb_path)
                worker.signals.finished.connect(self._on_sidebar_thumb_ready)
                thread_pool.start(worker)

        # Eğer şu an çalan bir video varsa listede hemen vurgula
        if hasattr(self, 'current_playing_path') and self.current_playing_path:
            self._highlight_active_sidebar_card(self.current_playing_path)

    def _on_sidebar_thumb_ready(self, video_path, thumb_path):
        if video_path in self.sidebar_cards_by_path:
            self.sidebar_cards_by_path[video_path].set_thumbnail(thumb_path)
        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ThisIsMyTubeApp() 
    window.show()
    sys.exit(app.exec())

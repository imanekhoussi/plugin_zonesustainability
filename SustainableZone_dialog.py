# -*- coding: utf-8 -*-
import os
import numpy as np
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtGui import QPixmap, QFont
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QLabel, QDoubleSpinBox, QFormLayout, QGroupBox, QVBoxLayout, QWidget
)
from qgis.core import QgsMapLayerProxyModel

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'SustainableZone_dialog_base.ui'))


# =====================================================================
#  Définition des sous-critères par dimension
# =====================================================================
SUB_CRITERIA = {
    'eco': ['PIB', 'Infra', 'Resto', 'Touristes'],
    'env': ['IQA', 'Ressources', 'Biodiversité'],
    'soc': ['Sécurité', 'Santé', 'Pauvreté', 'PMR'],
}

# RI (Random Index) pour matrices de taille n
RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
            6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


class SustainableZoneDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(SustainableZoneDialog, self).__init__(parent)
        self.setupUi(self)

        # Déconnecter accept() pour que OK ne ferme pas la fenêtre
        self.button_box.accepted.disconnect()
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setText("🚀 Lancer l'Analyse")

        self.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.mMapLayerComboBox.layerChanged.connect(self.update_fields)
        self.update_fields()

        # === AHP dimensions principales ===
        self.spin_eco_env.valueChanged.connect(self.update_ahp_weights)
        self.spin_eco_soc.valueChanged.connect(self.update_ahp_weights)
        self.spin_env_soc.valueChanged.connect(self.update_ahp_weights)
        self.update_ahp_weights()

        # === AHP sous-critères (dynamique) ===
        self._sub_ahp_spinboxes = {}   # { 'eco': {(i,j): spinbox}, ... }
        self._sub_ahp_labels = {}      # { 'eco': lbl_weights, ... }
        self._sub_ahp_cr_labels = {}   # { 'eco': lbl_cr, ... }
        self._sub_ahp_built = False

        self.chk_sub_ahp.stateChanged.connect(self._toggle_sub_ahp)

        # === Graph navigation ===
        self._graph_paths = []
        self._graph_index = 0
        self.btn_graph_prev.clicked.connect(self.show_prev_graph)
        self.btn_graph_next.clicked.connect(self.show_next_graph)

        # Results storage
        self._results = []

    # =================================================================
    #  Champs auto-détection
    # =================================================================
    def update_fields(self):
        layer = self.mMapLayerComboBox.currentLayer()
        mapping = {
            self.mField_PIB:       ['pib', 'gdp', 'chiffre', 'affaire', 'revenu'],
            self.mField_Infra:     ['infra', 'hotel', 'hebergement'],
            self.mField_Resto:     ['resto', 'restaurant', 'cafe', 'terroir', 'artisan'],
            self.mField_Touristes: ['tourist', 'visiteur'],
            self.mField_IQA:       ['iqa', 'air', 'climat', 'meteo', 'qualit'],
            self.mField_Ress:      ['ressource', 'nature', 'eau'],
            self.mField_Bio:       ['bio', 'diversite', 'faune'],
            self.mField_Secu:      ['secu', 'police', 'crime'],
            self.mField_Sante:     ['sante', 'social', 'tradition'],
            self.mField_Pauvrete:  ['pauvre', 'chomage', 'emploi'],
            self.mField_PMR:       ['pmr', 'mobilite', 'accueil', 'handicap'],
        }
        for combo in mapping.keys():
            combo.setLayer(layer)
            combo.setField(None)
        if not layer:
            return
        assigned = set()
        for field in layer.fields():
            name = field.name().lower()
            for combo, keywords in mapping.items():
                if combo in assigned:
                    continue
                for kw in keywords:
                    if kw in name:
                        combo.setField(field.name())
                        assigned.add(combo)
                        break

    # =================================================================
    #  AHP Générique (fonctionne pour n'importe quelle taille n)
    # =================================================================
    @staticmethod
    def compute_ahp_generic(matrix):
        """Calcul AHP générique pour une matrice nxn.
        Retourne (weights, CR).
        """
        n = matrix.shape[0]
        # Moyenne géométrique par ligne
        geo_means = np.prod(matrix, axis=1) ** (1.0 / n)
        weights = geo_means / geo_means.sum()

        # Ratio de cohérence
        Aw = matrix @ weights
        lambda_max = np.mean(Aw / weights)
        CI = (lambda_max - n) / max(n - 1, 1)
        ri = RI_TABLE.get(n, 1.49)
        CR = CI / ri if ri > 0 else 0.0
        return weights, CR

    # =================================================================
    #  AHP dimensions principales (3×3)
    # =================================================================
    def compute_ahp(self, eco_env, eco_soc, env_soc):
        eco_env = max(eco_env, 0.01)
        eco_soc = max(eco_soc, 0.01)
        env_soc = max(env_soc, 0.01)
        M = np.array([
            [1.0,         eco_env,     eco_soc],
            [1.0/eco_env, 1.0,         env_soc],
            [1.0/eco_soc, 1.0/env_soc, 1.0]
        ])
        return self.compute_ahp_generic(M)

    def update_ahp_weights(self):
        weights, cr = self.compute_ahp(
            self.spin_eco_env.value(),
            self.spin_eco_soc.value(),
            self.spin_env_soc.value()
        )
        self.ahp_weights = weights
        self.lbl_weights_result.setText(
            f"Économie: {weights[0]:.3f}  |  Environnement: {weights[1]:.3f}  |  Social: {weights[2]:.3f}"
        )
        if cr < 0.10:
            self.lbl_cr.setText(f"CR : {cr:.3f} ✔ Cohérent")
            self.lbl_cr.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.lbl_cr.setText(f"CR : {cr:.3f} ✘ Incohérent (> 0.10)")
            self.lbl_cr.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def get_weights(self):
        if hasattr(self, 'ahp_weights'):
            return self.ahp_weights
        return np.array([0.540, 0.297, 0.163])

    # =================================================================
    #  AHP sous-critères — Construction dynamique des spinboxes
    # =================================================================
    def _build_sub_ahp_ui(self):
        """Construit dynamiquement les GroupBox avec spinboxes pour chaque dimension."""
        if self._sub_ahp_built:
            return

        layout = self.vl_sub_ahp_content

        dim_config = {
            'eco': {'title': '📊 Économie — 4 sous-critères (6 paires)',
                    'color': '#3498db', 'names': SUB_CRITERIA['eco']},
            'env': {'title': '🌿 Environnement — 3 sous-critères (3 paires)',
                    'color': '#27ae60', 'names': SUB_CRITERIA['env']},
            'soc': {'title': '🤝 Social — 4 sous-critères (6 paires)',
                    'color': '#f39c12', 'names': SUB_CRITERIA['soc']},
        }

        for dim_key, cfg in dim_config.items():
            names = cfg['names']
            n = len(names)
            color = cfg['color']

            # GroupBox
            grp = QGroupBox(cfg['title'])
            grp.setStyleSheet(f"""
                QGroupBox {{
                    background-color: white; border: 1px solid {color};
                    border-radius: 5px; margin-top: 12px; font-weight: bold;
                    font-size: 11px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; left: 8px;
                    padding: 0 4px; color: {color};
                }}
            """)
            grp_layout = QVBoxLayout()
            grp_layout.setSpacing(3)

            # FormLayout pour les paires
            form = QFormLayout()
            form.setVerticalSpacing(3)
            form.setHorizontalSpacing(10)

            spinboxes = {}
            for i in range(n):
                for j in range(i + 1, n):
                    label_text = f"{names[i]} / {names[j]} :"
                    spin = QDoubleSpinBox()
                    spin.setMinimum(0.11)
                    spin.setMaximum(9.00)
                    spin.setSingleStep(0.5)
                    spin.setDecimals(2)
                    spin.setValue(1.00)  # Poids égaux par défaut
                    spin.setFixedWidth(80)
                    spin.valueChanged.connect(self._update_sub_ahp_weights)
                    spinboxes[(i, j)] = spin
                    form.addRow(label_text, spin)

            self._sub_ahp_spinboxes[dim_key] = spinboxes
            grp_layout.addLayout(form)

            # Label résultat poids
            lbl_w = QLabel("Poids : en attente...")
            lbl_w.setAlignment(Qt.AlignCenter)
            lbl_w.setWordWrap(True)
            lbl_w.setStyleSheet(
                f"color:{color}; font-size:10px; font-weight:bold; "
                f"padding:4px; background:#f9f9f9; border:1px solid {color}; border-radius:3px;"
            )
            self._sub_ahp_labels[dim_key] = lbl_w
            grp_layout.addWidget(lbl_w)

            # Label CR
            lbl_cr = QLabel("CR : —")
            lbl_cr.setAlignment(Qt.AlignCenter)
            lbl_cr.setStyleSheet("color:#7F8C8D; font-size:10px;")
            self._sub_ahp_cr_labels[dim_key] = lbl_cr
            grp_layout.addWidget(lbl_cr)

            grp.setLayout(grp_layout)
            layout.addWidget(grp)

        self._sub_ahp_built = True
        self._update_sub_ahp_weights()

    def _build_matrix_from_spinboxes(self, dim_key):
        """Reconstruit la matrice NxN à partir des spinboxes d'une dimension."""
        names = SUB_CRITERIA[dim_key]
        n = len(names)
        M = np.ones((n, n))
        spinboxes = self._sub_ahp_spinboxes.get(dim_key, {})
        for (i, j), spin in spinboxes.items():
            val = max(spin.value(), 0.01)
            M[i, j] = val
            M[j, i] = 1.0 / val
        return M

    def _update_sub_ahp_weights(self):
        """Recalcule les poids et CR pour chaque dimension de sous-critères."""
        for dim_key in ['eco', 'env', 'soc']:
            if dim_key not in self._sub_ahp_spinboxes:
                continue

            names = SUB_CRITERIA[dim_key]
            M = self._build_matrix_from_spinboxes(dim_key)
            weights, cr = self.compute_ahp_generic(M)

            # Afficher les poids
            parts = [f"{names[i]}: {weights[i]:.3f}" for i in range(len(names))]
            self._sub_ahp_labels[dim_key].setText(" | ".join(parts))

            # Afficher CR
            lbl_cr = self._sub_ahp_cr_labels[dim_key]
            if cr < 0.10:
                lbl_cr.setText(f"CR : {cr:.3f} ✔ Cohérent")
                lbl_cr.setStyleSheet("color: #27ae60; font-size: 10px;")
            else:
                lbl_cr.setText(f"CR : {cr:.3f} ✘ Incohérent (> 0.10)")
                lbl_cr.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def _toggle_sub_ahp(self, state):
        """Affiche/masque le panneau AHP sous-critères."""
        checked = (state == Qt.Checked)
        if checked and not self._sub_ahp_built:
            self._build_sub_ahp_ui()
        self.scrollArea_sub_ahp.setVisible(checked)

    # =================================================================
    #  Retourner les poids des sous-critères
    # =================================================================
    def get_sub_weights(self):
        """Retourne les poids des sous-critères pour chaque dimension.
        Si AHP détaillé activé → poids calculés via AHP.
        Sinon → poids égaux (moyenne simple).
        """
        if self.chk_sub_ahp.isChecked() and self._sub_ahp_built:
            w_eco, _ = self.compute_ahp_generic(self._build_matrix_from_spinboxes('eco'))
            w_env, _ = self.compute_ahp_generic(self._build_matrix_from_spinboxes('env'))
            w_soc, _ = self.compute_ahp_generic(self._build_matrix_from_spinboxes('soc'))
            return w_eco, w_env, w_soc
        else:
            return (np.ones(4) / 4.0,
                    np.ones(3) / 3.0,
                    np.ones(4) / 4.0)

    # =================================================================
    #  Graphiques navigation
    # =================================================================
    def set_graph_paths(self, paths):
        self._graph_paths = paths
        self._graph_index = 0
        if paths:
            self.show_graph(0)

    def show_graph(self, idx):
        if not self._graph_paths:
            return
        idx = idx % len(self._graph_paths)
        self._graph_index = idx
        path = self._graph_paths[idx]
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            display_w = max(self.lbl_graph_display.width(), 580)
            display_h = max(self.lbl_graph_display.height(), 400)
            scaled = pixmap.scaled(
                display_w, display_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_graph_display.setPixmap(scaled)
        name = os.path.basename(path).replace('.png', '').replace('_', ' ').title()
        self.lbl_graph_title.setText(f"{idx+1}/{len(self._graph_paths)} — {name}")

    def show_prev_graph(self):
        if self._graph_paths:
            self.show_graph(self._graph_index - 1)

    def show_next_graph(self):
        if self._graph_paths:
            self.show_graph(self._graph_index + 1)

    # =================================================================
    #  Comparaison
    # =================================================================
    def populate_compare_combos(self, results):
        self._results = results
        self.combo_zone1.clear()
        self.combo_zone2.clear()
        for r in results:
            self.combo_zone1.addItem(r['name'])
            self.combo_zone2.addItem(r['name'])
        if len(results) >= 2:
            self.combo_zone2.setCurrentIndex(1)
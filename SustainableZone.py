# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SustainableZone - Plugin ADMC Complet
 Conforme à l'énoncé : AHP + graphiques + PDF + comparaison
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon, QColor, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog
from qgis.core import (
    QgsField, QgsGraduatedSymbolRenderer, QgsRendererRange,
    QgsSymbol, Qgis, QgsProject
)
from .SustainableZone_dialog import SustainableZoneDialog
import os
import os.path
import re
import numpy as np

# ========== NORMES ==========
NORM_PIB   = 500.0;  NORM_INFRA = 400.0;  NORM_RESTO = 700.0;  NORM_TOUR = 1000.0
NORM_IQA   = 40.0;   NORM_RESS  = 600.0;  NORM_BIO   = 900.0
NORM_SECU  = 68.0;   NORM_SANTE = 60.0;   NORM_PAUV  = 50.0;   NORM_PMR  = 50.0

SUB_NAMES_ECO = ['PIB', 'Infrastructures', 'Restaurants', 'Touristes']
SUB_NAMES_ENV = ['IQA', 'Ressources', 'Biodiversité']
SUB_NAMES_SOC = ['Sécurité', 'Santé', 'Pauvreté', 'PMR']

INVERTED_CRITERIA = {'pauv'}


class SustainableZone:
    def __init__(self, iface):
        self.iface = iface
        self.dlg = None
        self._results = []
        self._buttons_connected = False

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            u"Calculer ADMC", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(u"&SustainableZone", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu(u"&SustainableZone", self.action)
        self.iface.removeToolBarIcon(self.action)

    def log(self, msg, color="white", bold=False):
        style = f"color:{color}; font-family:Consolas;"
        if bold:
            style += " font-weight:bold;"
        self.dlg.textBrowser_results.append(f"<span style='{style}'>{msg}</span>")
        QCoreApplication.processEvents()

    def safe_float(self, val):
        try:
            if val is None or val == "" or str(val).strip() == "NULL":
                return 0.0
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def safe_field_value(self, feature, field_name):
        if not field_name:
            return 0.0
        try:
            val = feature[field_name]
            return val
        except (KeyError, IndexError):
            return 0.0

    def norm_ratio(self, val, norm, invert=False):
        v = self.safe_float(val)
        ratio = v / norm if norm > 0 else 0.0
        if invert:
            ratio = max(0.0, 1.0 - ratio)
        return ratio

    def generate_advice(self, n_eco, n_env, n_soc):
        if n_env < 0.5:
            return "URGENCE ÉCOLOGIQUE : biodiversité et qualité air."
        if n_soc < 0.5:
            return "RISQUE SOCIAL : sécurité, santé, accessibilité."
        if n_eco < 0.5:
            return "DÉFICIT ÉCO : infrastructures et attractivité."
        if n_eco > 1.2 and n_env < 0.8:
            return "SURCHAUFFE : limiter tourisme de masse."
        return "Modèle équilibré : maintenir le cap."

    def safe_filename(self, name):
        return re.sub(r'[^\w\-]', '_', str(name))

    # ==================== GRAPHIQUES ====================
    def generate_charts(self, results, stats, w_eco, w_env, w_soc, output_dir):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            self.log("⚠ matplotlib indisponible.", "#f39c12")
            return []

        os.makedirs(output_dir, exist_ok=True)
        paths = []

        # 1. Camembert poids AHP
        try:
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.pie([w_eco, w_env, w_soc],
                   labels=[f'Économie\n({w_eco:.1%})', f'Environnement\n({w_env:.1%})',
                           f'Social\n({w_soc:.1%})'],
                   colors=['#3498db', '#27ae60', '#f39c12'],
                   autopct='%1.1f%%', startangle=90, textprops={'fontsize': 11})
            ax.set_title('Pondérations AHP des dimensions', fontsize=14, fontweight='bold')
            p = os.path.join(output_dir, "01_pie_ahp.png")
            fig.savefig(p, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths.append(p)
        except Exception as e:
            self.log(f"⚠ Erreur graphique camembert AHP : {e}", "#f39c12")

        # 2. Barres scores pondérés
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            names = [r['name'] for r in results]
            x = np.arange(len(names))
            w = 0.25
            ax.bar(x - w, [r['ws_eco'] for r in results], w, label='Économie', color='#3498db')
            ax.bar(x,     [r['ws_env'] for r in results], w, label='Environnement', color='#27ae60')
            ax.bar(x + w, [r['ws_soc'] for r in results], w, label='Social', color='#f39c12')
            ax.set_ylabel('Score pondéré AHP')
            ax.set_title('Scores pondérés par dimension', fontsize=14, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(names, rotation=30, ha='right')
            ax.legend()
            ax.grid(axis='y', alpha=0.3)
            p = os.path.join(output_dir, "02_bar_scores.png")
            fig.savefig(p, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths.append(p)
        except Exception as e:
            self.log(f"⚠ Erreur graphique barres scores : {e}", "#f39c12")

        # 3. Barres indice global
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            names = [r['name'] for r in results]
            id_vals = [r['id_global'] for r in results]
            colors = ['#27ae60' if v >= 0.8 else '#f39c12' if v >= 0.5 else '#e74c3c'
                      for v in id_vals]
            bars = ax.bar(names, id_vals, color=colors)
            ax.axhline(y=0.8, color='#27ae60', linestyle='--', label='Seuil durable')
            ax.axhline(y=0.5, color='#f39c12', linestyle='--', label='Seuil transition')
            ax.set_ylabel('Score global')
            ax.set_title('Indice de durabilité global', fontsize=14, fontweight='bold')
            ax.legend()
            ax.grid(axis='y', alpha=0.3)
            for bar, val in zip(bars, id_vals):
                ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.01,
                        f'{val:.2f}', ha='center', va='bottom', fontweight='bold')
            plt.xticks(rotation=30, ha='right')
            p = os.path.join(output_dir, "03_bar_global.png")
            fig.savefig(p, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths.append(p)
        except Exception as e:
            self.log(f"⚠ Erreur graphique indice global : {e}", "#f39c12")

        # 4. Camembert durabilité
        try:
            fig, ax = plt.subplots(figsize=(7, 5))
            ld, vd, cd = [], [], []
            for lbl, cnt, col in [('Durables', stats.get('Durable', 0), '#27ae60'),
                                   ('Transition', stats.get('Transition', 0), '#f39c12'),
                                   ('Critiques', stats.get('Critique', 0), '#e74c3c')]:
                if cnt > 0:
                    ld.append(lbl)
                    vd.append(cnt)
                    cd.append(col)
            if vd:
                ax.pie(vd, labels=ld, colors=cd, autopct='%1.0f%%', startangle=90,
                       textprops={'fontsize': 12})
                ax.set_title('ÉTATS DE DURABILITÉ', fontsize=14, fontweight='bold')
            p = os.path.join(output_dir, "04_pie_durabilite.png")
            fig.savefig(p, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths.append(p)
        except Exception as e:
            self.log(f"⚠ Erreur graphique camembert durabilité : {e}", "#f39c12")

        # 5. Radar par zone
        for r in results:
            try:
                fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
                cats = ['Économie', 'Environnement', 'Social']
                vals = [r['norm_eco'], r['norm_env'], r['norm_soc']] + [r['norm_eco']]
                angles = np.linspace(0, 2 * np.pi, 3, endpoint=False).tolist() + [0]
                ax.fill(angles, vals, color='#27ae60', alpha=0.25)
                ax.plot(angles, vals, color='#27ae60', linewidth=2, marker='o')
                ax.set_thetagrids(np.degrees(angles[:-1]), cats)
                ax.set_title(f"Profil — {r['name']}", fontsize=13, fontweight='bold')
                safe_name = self.safe_filename(r['name'])
                p = os.path.join(output_dir, f"05_radar_{safe_name}.png")
                fig.savefig(p, dpi=200, bbox_inches='tight')
                plt.close(fig)
                paths.append(p)
            except Exception as e:
                self.log(f"⚠ Erreur radar {r['name']} : {e}", "#f39c12")

        # 6. Détail sous-critères
        try:
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            n_zones = len(results)
            bar_height = 0.8 / max(n_zones, 1)
            for idx, r in enumerate(results):
                offset = (idx - n_zones / 2.0 + 0.5) * bar_height
                y_eco = np.arange(len(SUB_NAMES_ECO)) + offset
                y_env = np.arange(len(SUB_NAMES_ENV)) + offset
                y_soc = np.arange(len(SUB_NAMES_SOC)) + offset
                axes[0].barh(y_eco, r['subs_eco'], height=bar_height, label=r['name'], alpha=0.7)
                axes[1].barh(y_env, r['subs_env'], height=bar_height, label=r['name'], alpha=0.7)
                axes[2].barh(y_soc, r['subs_soc'], height=bar_height, label=r['name'], alpha=0.7)
            for ax, title, names_list in zip(axes,
                                              ['Économie', 'Environnement', 'Social'],
                                              [SUB_NAMES_ECO, SUB_NAMES_ENV, SUB_NAMES_SOC]):
                ax.set_yticks(np.arange(len(names_list)))
                ax.set_yticklabels(names_list)
                ax.set_title(title, fontweight='bold')
                ax.axvline(x=1.0, color='red', linestyle='--', alpha=0.5)
                ax.legend(fontsize=8)
                ax.grid(axis='x', alpha=0.3)
            fig.suptitle('Détail des sous-critères normalisés', fontsize=14, fontweight='bold')
            plt.tight_layout()
            p = os.path.join(output_dir, "06_detail_sous_criteres.png")
            fig.savefig(p, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths.append(p)
        except Exception as e:
            self.log(f"⚠ Erreur graphique sous-critères : {e}", "#f39c12")

        return paths

    # ==================== COMPARAISON ====================
    def compare_zones(self):
        if not self._results or len(self._results) < 2:
            self.dlg.lbl_compare_result.setText("Lancez d'abord l'analyse.")
            return
        i1 = self.dlg.combo_zone1.currentIndex()
        i2 = self.dlg.combo_zone2.currentIndex()
        if i1 == i2:
            self.dlg.lbl_compare_result.setText("Choisissez 2 zones différentes.")
            return
        if i1 < 0 or i1 >= len(self._results) or i2 < 0 or i2 >= len(self._results):
            self.dlg.lbl_compare_result.setText("Index de zone invalide.")
            return
        r1, r2 = self._results[i1], self._results[i2]

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                            subplot_kw=dict(polar=True))
            cats = ['Économie', 'Environnement', 'Social']
            angles = np.linspace(0, 2 * np.pi, 3, endpoint=False).tolist() + [0]

            for ax, r, col in [(ax1, r1, '#3498db'), (ax2, r2, '#e74c3c')]:
                vals = [r['norm_eco'], r['norm_env'], r['norm_soc']] + [r['norm_eco']]
                ax.fill(angles, vals, alpha=0.25, color=col)
                ax.plot(angles, vals, color=col, linewidth=2, marker='o')
                ax.set_thetagrids(np.degrees(angles[:-1]), cats)
                ax.set_title(f"{r['name']}\nId={r['id_global']:.3f} ({r['classe']})",
                             fontsize=11, fontweight='bold')

            fig.suptitle(f"Comparaison : {r1['name']}  VS  {r2['name']}",
                         fontsize=14, fontweight='bold')
            plt.tight_layout()
            cmp_path = os.path.join(os.path.dirname(__file__), 'charts', 'comparaison.png')
            os.makedirs(os.path.dirname(cmp_path), exist_ok=True)
            fig.savefig(cmp_path, dpi=200, bbox_inches='tight')
            plt.close(fig)

            pixmap = QPixmap(cmp_path)
            if not pixmap.isNull():
                from qgis.PyQt.QtCore import Qt
                display_w = max(self.dlg.lbl_compare_result.width(), 500)
                display_h = max(self.dlg.lbl_compare_result.height(), 300)
                scaled = pixmap.scaled(
                    display_w - 10,
                    display_h - 10,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.dlg.lbl_compare_result.setPixmap(scaled)
        except ImportError:
            self._compare_fallback_text(r1, r2)
        except Exception as e:
            self.dlg.lbl_compare_result.setText(f"Erreur comparaison : {e}")

    def _compare_fallback_text(self, r1, r2):
        html = f"""<table style='width:100%; font-size:12px;'>
        <tr><th></th><th style='color:#3498db'>{r1['name']}</th>
            <th style='color:#e74c3c'>{r2['name']}</th><th>Δ</th></tr>
        <tr><td>Économie</td><td>{r1['norm_eco']:.2f}</td>
            <td>{r2['norm_eco']:.2f}</td><td>{r1['norm_eco'] - r2['norm_eco']:+.2f}</td></tr>
        <tr><td>Environnement</td><td>{r1['norm_env']:.2f}</td>
            <td>{r2['norm_env']:.2f}</td><td>{r1['norm_env'] - r2['norm_env']:+.2f}</td></tr>
        <tr><td>Social</td><td>{r1['norm_soc']:.2f}</td>
            <td>{r2['norm_soc']:.2f}</td><td>{r1['norm_soc'] - r2['norm_soc']:+.2f}</td></tr>
        <tr style='font-weight:bold'><td>Global</td><td>{r1['id_global']:.3f}</td>
            <td>{r2['id_global']:.3f}</td><td>{r1['id_global'] - r2['id_global']:+.3f}</td></tr>
        <tr><td>Classe</td><td>{r1['classe']}</td><td>{r2['classe']}</td><td></td></tr>
        </table>"""
        self.dlg.lbl_compare_result.setText(html)

    # ==================== EXPORT PDF ====================
    def export_pdf(self):
        if not self._results:
            QMessageBox.warning(self.dlg, "Erreur", "Lancez d'abord l'analyse.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self.dlg, "Exporter le rapport PDF", "", "PDF (*.pdf)")
        if not path:
            return

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages

            charts_dir = os.path.join(os.path.dirname(__file__), 'charts')
            with PdfPages(path) as pdf:
                # Page titre
                fig, ax = plt.subplots(figsize=(11, 8.5))
                ax.axis('off')
                ax.text(0.5, 0.7, 'Rapport ADMC', fontsize=36, fontweight='bold',
                        ha='center', color='#2c3e50')
                ax.text(0.5, 0.6, 'Évaluation de Durabilité Touristique', fontsize=20,
                        ha='center', color='#27ae60')
                ax.text(0.5, 0.45, f'{len(self._results)} zones analysées', fontsize=16,
                        ha='center', color='#7f8c8d')
                w = self.dlg.get_weights()
                ax.text(0.5, 0.35,
                        f'Poids AHP : Éco={w[0]:.3f}  Env={w[1]:.3f}  Soc={w[2]:.3f}',
                        fontsize=12, ha='center', color='#7f8c8d')
                pdf.savefig(fig)
                plt.close(fig)

                # Page résultats tableau
                fig, ax = plt.subplots(figsize=(11, 8.5))
                ax.axis('off')
                table_data = [['Zone', 'Éco', 'Env', 'Soc', 'Global', 'Classe', 'Conseil']]
                for r in self._results:
                    table_data.append([
                        r['name'][:20], f"{r['norm_eco']:.2f}", f"{r['norm_env']:.2f}",
                        f"{r['norm_soc']:.2f}", f"{r['id_global']:.3f}",
                        r['classe'], r['conseil'][:30]
                    ])

                table = ax.table(cellText=table_data, loc='center', cellLoc='center')
                table.auto_set_font_size(False)
                table.set_fontsize(9)
                table.scale(1, 1.8)
                for j in range(7):
                    table[0, j].set_facecolor('#2c3e50')
                    table[0, j].set_text_props(color='white', fontweight='bold')
                for i, r in enumerate(self._results, 1):
                    c = ('#d5f5e3' if r['classe'] == 'Durable'
                         else '#fdebd0' if r['classe'] == 'Transition'
                         else '#fadbd8')
                    for j in range(7):
                        table[i, j].set_facecolor(c)
                ax.set_title('Résultats détaillés', fontsize=16, fontweight='bold', pad=20)
                pdf.savefig(fig)
                plt.close(fig)

                # Pages graphiques
                if os.path.isdir(charts_dir):
                    chart_files = sorted(
                        [f for f in os.listdir(charts_dir) if f.endswith('.png')])
                    for cf in chart_files:
                        img_path = os.path.join(charts_dir, cf)
                        fig, ax = plt.subplots(figsize=(11, 8.5))
                        ax.axis('off')
                        img = plt.imread(img_path)
                        ax.imshow(img)
                        pdf.savefig(fig)
                        plt.close(fig)

            self.log(f"  📄 PDF exporté → {path}", "#2ecc71")
            QMessageBox.information(self.dlg, "Succès",
                                    f"Rapport PDF exporté :\n{path}")

        except ImportError:
            QMessageBox.critical(self.dlg, "Erreur PDF",
                                 "matplotlib est requis pour l'export PDF.")
        except Exception as e:
            QMessageBox.critical(self.dlg, "Erreur PDF", str(e))

    # ==================== VALIDATION CHAMPS ====================
    def validate_fields(self, ui):
        missing = []
        field_labels = {
            'pib': 'PIB', 'infra': 'Infrastructures', 'resto': 'Restaurants',
            'tour': 'Touristes', 'iqa': 'IQA', 'ress': 'Ressources',
            'bio': 'Biodiversité', 'secu': 'Sécurité', 'sante': 'Santé',
            'pauv': 'Pauvreté', 'pmr': 'PMR'
        }
        for key, label in field_labels.items():
            if not ui.get(key):
                missing.append(label)
        return missing

    # ==================== LANCER L'ANALYSE ====================
    def launch_analysis(self):
        """Exécute l'analyse SANS fermer la fenêtre."""
        layer = self.dlg.mMapLayerComboBox.currentLayer()
        if not layer:
            QMessageBox.warning(self.dlg, "Erreur", "Sélectionnez une couche.")
            return

        self.dlg.progressBar.setValue(0)
        self.dlg.progressBar.setFormat("Analyse en cours...")
        self.dlg.textBrowser_results.clear()
        self.log(">> DÉMARRAGE ADMC...", "#3498db", True)

        weights = self.dlg.get_weights()
        w_eco, w_env, w_soc = weights[0], weights[1], weights[2]
        self.log(f"  Poids AHP : Éco={w_eco:.3f} Env={w_env:.3f} Soc={w_soc:.3f}", "#9b59b6")

        ui = {
            'pib': self.dlg.mField_PIB.currentField(),
            'infra': self.dlg.mField_Infra.currentField(),
            'resto': self.dlg.mField_Resto.currentField(),
            'tour': self.dlg.mField_Touristes.currentField(),
            'iqa': self.dlg.mField_IQA.currentField(),
            'ress': self.dlg.mField_Ress.currentField(),
            'bio': self.dlg.mField_Bio.currentField(),
            'secu': self.dlg.mField_Secu.currentField(),
            'sante': self.dlg.mField_Sante.currentField(),
            'pauv': self.dlg.mField_Pauvrete.currentField(),
            'pmr': self.dlg.mField_PMR.currentField(),
        }

        missing = self.validate_fields(ui)
        if missing:
            QMessageBox.warning(
                self.dlg, "Champs manquants",
                f"Les champs suivants ne sont pas sélectionnés :\n• "
                + "\n• ".join(missing)
                + "\n\nVeuillez les configurer dans les onglets correspondants.")
            return

        layer.startEditing()
        res_fields = [
            QgsField("Score_Eco", QVariant.Double),
            QgsField("Score_Env", QVariant.Double),
            QgsField("Score_Soc", QVariant.Double),
            QgsField("Id_Global", QVariant.Double),
            QgsField("Classe_ADMC", QVariant.String),
            QgsField("Conseil", QVariant.String)
        ]
        for rf in res_fields:
            if layer.fields().indexOf(rf.name()) == -1:
                layer.dataProvider().addAttributes([rf])
        layer.updateFields()

        feats = list(layer.getFeatures())
        count = len(feats)
        if count == 0:
            self.log(">> Couche vide.", "#e74c3c", True)
            layer.rollBack()
            return

        use_sub_ahp = self.dlg.chk_sub_ahp.isChecked()
        if use_sub_ahp:
            sub_w_eco, sub_w_env, sub_w_soc = self.dlg.get_sub_weights()
            self.log("  AHP détaillé sous-critères : activé", "#9b59b6")
        else:
            sub_w_eco = np.ones(4) / 4.0
            sub_w_env = np.ones(3) / 3.0
            sub_w_soc = np.ones(4) / 4.0

        stats = {'Durable': 0, 'Transition': 0, 'Critique': 0}
        results = []

        for i, f in enumerate(feats):
            s_eco = [
                self.norm_ratio(self.safe_field_value(f, ui['pib']), NORM_PIB),
                self.norm_ratio(self.safe_field_value(f, ui['infra']), NORM_INFRA),
                self.norm_ratio(self.safe_field_value(f, ui['resto']), NORM_RESTO),
                self.norm_ratio(self.safe_field_value(f, ui['tour']), NORM_TOUR)
            ]
            s_env = [
                self.norm_ratio(self.safe_field_value(f, ui['iqa']), NORM_IQA),
                self.norm_ratio(self.safe_field_value(f, ui['ress']), NORM_RESS),
                self.norm_ratio(self.safe_field_value(f, ui['bio']), NORM_BIO)
            ]
            s_soc = [
                self.norm_ratio(self.safe_field_value(f, ui['secu']), NORM_SECU),
                self.norm_ratio(self.safe_field_value(f, ui['sante']), NORM_SANTE),
                self.norm_ratio(self.safe_field_value(f, ui['pauv']), NORM_PAUV, invert=True),
                self.norm_ratio(self.safe_field_value(f, ui['pmr']), NORM_PMR)
            ]

            norm_eco = np.dot(s_eco, sub_w_eco)
            norm_env = np.dot(s_env, sub_w_env)
            norm_soc = np.dot(s_soc, sub_w_soc)

            ws_eco = norm_eco * w_eco
            ws_env = norm_env * w_env
            ws_soc = norm_soc * w_soc
            id_global = ws_eco + ws_env + ws_soc

            conseil = self.generate_advice(norm_eco, norm_env, norm_soc)
            if id_global >= 0.8:
                classe = "Durable"
                stats['Durable'] += 1
            elif id_global >= 0.5:
                classe = "Transition"
                stats['Transition'] += 1
            else:
                classe = "Critique"
                stats['Critique'] += 1

            fname = f.attribute(0) if f.attribute(0) else f"Entité {f.id()}"
            self.log(
                f"  [{fname}] Éco={norm_eco:.2f} Env={norm_env:.2f} Soc={norm_soc:.2f} "
                f"Id={id_global:.3f} → {classe}",
                "#2ecc71" if classe == "Durable"
                else "#f39c12" if classe == "Transition"
                else "#e74c3c")

            f['Score_Eco'] = float(ws_eco)
            f['Score_Env'] = float(ws_env)
            f['Score_Soc'] = float(ws_soc)
            f['Id_Global'] = float(id_global)
            f['Classe_ADMC'] = classe
            f['Conseil'] = conseil
            layer.updateFeature(f)

            results.append({
                'name': str(fname),
                'norm_eco': norm_eco, 'norm_env': norm_env, 'norm_soc': norm_soc,
                'ws_eco': ws_eco, 'ws_env': ws_env, 'ws_soc': ws_soc,
                'subs_eco': s_eco, 'subs_env': s_env, 'subs_soc': s_soc,
                'id_global': id_global, 'classe': classe, 'conseil': conseil
            })
            self.dlg.progressBar.setValue(int(((i + 1) / count) * 100))

        layer.commitChanges()
        self.apply_style(layer)

        self._results = results

        # Graphiques
        charts_dir = os.path.join(os.path.dirname(__file__), 'charts')
        graph_paths = self.generate_charts(results, stats, w_eco, w_env, w_soc, charts_dir)
        self.dlg.set_graph_paths(graph_paths)
        self.log(f"  📊 {len(graph_paths)} graphiques générés", "#2ecc71")

        # Comparaison
        self.dlg.populate_compare_combos(results)

        # Bilan
        total = sum(stats.values())
        self.log(f"""
        <br><b style='color:#3498db'>━━━ BILAN ━━━</b><br>
        <table><tr><td style='color:#27ae60'>✔ Durables:</td><td><b>{stats['Durable']}</b></td></tr>
        <tr><td style='color:#f39c12'>⚠ Transition:</td><td><b>{stats['Transition']}</b></td></tr>
        <tr><td style='color:#e74c3c'>✘ Critiques:</td><td><b>{stats['Critique']}</b></td></tr></table>
        <br><i>→ Onglet Graphiques pour visualiser | Onglet Comparer pour comparer 2 zones | Bouton PDF pour exporter</i>""")

        self.dlg.progressBar.setValue(100)
        self.dlg.progressBar.setFormat("100% - Terminée")
        self.dlg.tabWidget.setCurrentIndex(4)  # Aller à l'onglet graphiques
        self.iface.messageBar().pushMessage(
            "ADMC", f"{total} zones analysées", level=Qgis.Success)

    # ==================== MOTEUR PRINCIPAL ====================
    def run(self):
        """Ouvre la fenêtre et connecte le bouton OK à l'analyse."""
        # Recréer le dialogue à chaque ouverture pour éviter les états résiduels
        self.dlg = SustainableZoneDialog(self.iface.mainWindow())

        # Connecter le bouton OK à l'analyse (PAS à accept/fermer)
        self.dlg.button_box.accepted.connect(self.launch_analysis)

        # Connecter les autres boutons
        self.dlg.btn_compare.clicked.connect(self.compare_zones)
        self.dlg.btn_export_pdf.clicked.connect(self.export_pdf)

        self._results = []

        # show() au lieu de exec_() : la fenêtre reste ouverte
        self.dlg.show()

    def apply_style(self, layer):
        ranges = [
            QgsRendererRange(0.0, 0.5,
                             QgsSymbol.defaultSymbol(layer.geometryType()), "Critique"),
            QgsRendererRange(0.5, 0.8,
                             QgsSymbol.defaultSymbol(layer.geometryType()), "Transition"),
            QgsRendererRange(0.8, 5.0,
                             QgsSymbol.defaultSymbol(layer.geometryType()), "Durable")
        ]
        ranges[0].symbol().setColor(QColor("#e74c3c"))
        ranges[1].symbol().setColor(QColor("#f39c12"))
        ranges[2].symbol().setColor(QColor("#27ae60"))
        renderer = QgsGraduatedSymbolRenderer("Id_Global", ranges)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())
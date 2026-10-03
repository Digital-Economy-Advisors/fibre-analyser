# -*- coding: utf-8 -*-
"""
Fibre Analyzer
A QGIS Plugin for calculating financial viability of fibre deployments
Author: Clinton
Version: 1.1 Fixes ben Roberts
"""
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout,
                                 QPushButton, QLabel, QComboBox,
                                 QTableWidget, QTableWidgetItem, QMessageBox,
                                 QGroupBox, QTextEdit)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (QgsProject, QgsGeometry, QgsFeature, QgsVectorLayer,
                       QgsPointXY, QgsRectangle, QgsWkbTypes, QgsFeatureRequest,
                       QgsDistanceArea, QgsUnitTypes)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.utils import iface
import math
import os

class FibreAnalyzer:
    """Main plugin class"""
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dialog = None
        self.action = None
        
        # Default reference data
        self.reference_data = {
            'Dense Urban': {
                'Cost_Per_Meter_Aerial': 5.00, 'Cost_Per_Meter_Trench': 10.00,
                'Avg_Monthly_ARPU': 60.00, 'Take_Rate_Initial': 0.60,
                'Capex_Per_Home_Connect': 300.00, 'Opex_Fixed_Annual': 8000.00,
                'Backhaul_Cost_Monthly': 500.00
            },
            'Urban': {
                'Cost_Per_Meter_Aerial': 6.50, 'Cost_Per_Meter_Trench': 14.00,
                'Avg_Monthly_ARPU': 50.00, 'Take_Rate_Initial': 0.50,
                'Capex_Per_Home_Connect': 350.00, 'Opex_Fixed_Annual': 10000.00,
                'Backhaul_Cost_Monthly': 600.00
            },
            'Suburbs': {
                'Cost_Per_Meter_Aerial': 7.50, 'Cost_Per_Meter_Trench': 16.00,
                'Avg_Monthly_ARPU': 48.00, 'Take_Rate_Initial': 0.48,
                'Capex_Per_Home_Connect': 400.00, 'Opex_Fixed_Annual': 11000.00,
                'Backhaul_Cost_Monthly': 700.00
            },
            'Semi-Rural': {
                'Cost_Per_Meter_Aerial': 8.50, 'Cost_Per_Meter_Trench': 18.00,
                'Avg_Monthly_ARPU': 45.00, 'Take_Rate_Initial': 0.45,
                'Capex_Per_Home_Connect': 450.00, 'Opex_Fixed_Annual': 12000.00,
                'Backhaul_Cost_Monthly': 800.00
            },
            'Rural': {
                'Cost_Per_Meter_Aerial': 12.00, 'Cost_Per_Meter_Trench': 28.00,
                'Avg_Monthly_ARPU': 35.00, 'Take_Rate_Initial': 0.30,
                'Capex_Per_Home_Connect': 650.00, 'Opex_Fixed_Annual': 18000.00,
                'Backhaul_Cost_Monthly': 1500.00
            },
            'Deep-Rural': {
                'Cost_Per_Meter_Aerial': 15.50, 'Cost_Per_Meter_Trench': 45.00,
                'Avg_Monthly_ARPU': 25.00, 'Take_Rate_Initial': 0.15,
                'Capex_Per_Home_Connect': 950.00, 'Opex_Fixed_Annual': 25000.00,
                'Backhaul_Cost_Monthly': 3200.00
            }
        }
        
    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            "Fibre Analyzer",  # ← Changed name
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.action.setStatusTip("Calculate financial viability of fibre deployments")
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Fibre Analyzer", self.action)  # ← Changed menu name
        
    def unload(self):
        self.iface.removePluginMenu("&Fibre Analyzer", self.action)  # ← Changed
        self.iface.removeToolBarIcon(self.action)
       
    def run(self):
        self.dialog = FibreAnalyzerDialog(self.reference_data, self.iface)
        self.dialog.show()


class PolygonMapTool(QgsMapTool):
    def __init__(self, canvas, callback):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.callback = callback
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 100))
        self.rubberBand.setWidth(2)
        self.points = []
        self.is_drawing = False
       
    def canvasPressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.toMapCoordinates(event.pos())
            self.points.append(point)
            self.rubberBand.addPoint(point, True)
            self.is_drawing = True
        elif event.button() == Qt.MouseButton.RightButton and self.is_drawing:
            if len(self.points) >= 3:
                ring = self.points[:]
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                polygon = QgsGeometry.fromPolygonXY([ring])
                self.callback(polygon)
            else:
                self.callback(None)
            self.reset()
           
    def reset(self):
        self.points = []
        self.rubberBand.reset()
        self.is_drawing = False
       
    def deactivate(self):
        self.reset()
        super().deactivate()


class FibreAnalyzerDialog(QDialog):  # ← Class name changed
    def __init__(self, reference_data, iface):
        super().__init__()
        self.reference_data = reference_data
        self.iface = iface
        self.selected_polygon = None
        self.selected_area_m2 = 0.0
        self.map_tool = None
        self.distance_calc = QgsDistanceArea()
        self.distance_calc.setEllipsoid('WGS84')
        self.area_unit = QgsUnitTypes.AreaSquareMeters
        self.area_unit_name = "m²"
        
        self.init_ui()
    
    def update_area_display(self):
        if self.selected_area_m2 <= 0:
            return
            
        unit = self.unit_combo.currentData()
        display_area = self.distance_calc.convertAreaMeasurement(
            self.selected_area_m2, unit
        )
        unit_name = self.unit_combo.currentText()
        
        self.area_status.setText(f"Area selected: {display_area:,.2f} {unit_name}")
        self.area_status.setStyleSheet("color: green; font-weight: bold;")
        
        self.area_unit = unit
        self.area_unit_name = unit_name
    
    def polygon_drawn(self, polygon):
        if polygon is None:
            QMessageBox.warning(
                self, "Warning", "At least three points are required to draw an area."
            )
            return

        if not polygon.isGeosValid():
            QMessageBox.warning(self, "Warning", "Invalid polygon drawn. Please try again.")
            self.reset_drawing()
            return
            
        canvas = self.iface.mapCanvas()
        self.distance_calc.setSourceCrs(
            canvas.mapSettings().destinationCrs(),
            QgsProject.instance().transformContext()
        )
        area_m2 = self.distance_calc.measureArea(polygon)
        if not math.isfinite(area_m2) or area_m2 <= 0:
            QMessageBox.warning(
                self, "Warning",
                "Could not measure the selected area. Check the map coordinate reference system and draw the area again."
            )
            self.reset_drawing()
            return

        self.selected_polygon = polygon
        self.selected_area_m2 = area_m2
        self.update_area_display()
        canvas.unsetMapTool(self.map_tool)
    
    def reset_drawing(self):
        if self.map_tool:
            self.map_tool.reset()
            self.iface.mapCanvas().unsetMapTool(self.map_tool)
        self.selected_polygon = None
        self.area_status.setText("No area selected")
        self.area_status.setStyleSheet("color: gray; font-style: italic;")
        self.selected_area_m2 = 0.0
    
    def start_drawing(self):
        canvas = self.iface.mapCanvas()
        self.map_tool = PolygonMapTool(canvas, self.polygon_drawn)
        canvas.setMapTool(self.map_tool)
        self.area_status.setText("Drawing mode active - Left click points, Right click finish")
        self.area_status.setStyleSheet("color: blue; font-weight: bold;")
    
    def populate_point_layers(self):
        self.household_combo.clear()
        self.household_combo.addItem("-- None (estimate) --", None)
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.household_combo.addItem(layer.name(), layer)
    
    def populate_line_layers(self):
        self.road_combo.clear()
        self.road_combo.addItem("-- None (estimate) --", None)
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.road_combo.addItem(layer.name(), layer)
    
    def count_points_in_polygon(self, layer, polygon):
        count = 0
        request = QgsFeatureRequest().setFilterRect(polygon.boundingBox())
        for feature in layer.getFeatures(request):
            if polygon.contains(feature.geometry()):
                count += 1
        return count
    
    def measure_lines_in_polygon(self, layer, polygon):
        total_length = 0.0
        request = QgsFeatureRequest().setFilterRect(polygon.boundingBox())
        for feature in layer.getFeatures(request):
            geom = feature.geometry()
            if polygon.intersects(geom):
                intersection = polygon.intersection(geom)
                if not intersection.isNull():
                    total_length += self.distance_calc.measureLength(intersection)
        return total_length
    
    def update_ref_table(self):
        self.ref_table.setRowCount(len(self.reference_data))
        row = 0
        for rtype, data in self.reference_data.items():
            self.ref_table.setItem(row, 0, QTableWidgetItem(rtype))
            self.ref_table.setItem(row, 1, QTableWidgetItem(str(data['Cost_Per_Meter_Aerial'])))
            self.ref_table.setItem(row, 2, QTableWidgetItem(str(data['Cost_Per_Meter_Trench'])))
            self.ref_table.setItem(row, 3, QTableWidgetItem(str(data['Avg_Monthly_ARPU'])))
            self.ref_table.setItem(row, 4, QTableWidgetItem(str(data['Take_Rate_Initial'])))
            self.ref_table.setItem(row, 5, QTableWidgetItem(str(data['Capex_Per_Home_Connect'])))
            self.ref_table.setItem(row, 6, QTableWidgetItem(str(data['Opex_Fixed_Annual'])))
            self.ref_table.setItem(row, 7, QTableWidgetItem(str(data['Backhaul_Cost_Monthly'])))
            row += 1
    
    def save_ref_changes(self):
        new_data = {}
        field_cols = {
            'Cost_Per_Meter_Aerial': 1,
            'Cost_Per_Meter_Trench': 2,
            'Avg_Monthly_ARPU': 3,
            'Take_Rate_Initial': 4,
            'Capex_Per_Home_Connect': 5,
            'Opex_Fixed_Annual': 6,
            'Backhaul_Cost_Monthly': 7
        }
        
        averages = {field: [] for field in field_cols}
        for r in range(self.ref_table.rowCount()):
            for field, col in field_cols.items():
                item = self.ref_table.item(r, col)
                if item and item.text().strip():
                    try:
                        averages[field].append(float(item.text()))
                    except ValueError:
                        pass
        
        avg_values = {f: sum(v)/len(v) if v else 0.0 for f, v in averages.items()}
        
        for r in range(self.ref_table.rowCount()):
            rtype_item = self.ref_table.item(r, 0)
            if not rtype_item or not rtype_item.text().strip():
                continue
            rtype = rtype_item.text().strip()
            data = {}
            for field, col in field_cols.items():
                item = self.ref_table.item(r, col)
                try:
                    data[field] = float(item.text()) if item and item.text().strip() else avg_values[field]
                except:
                    data[field] = avg_values[field]
            new_data[rtype] = data
        
        if new_data:
            self.reference_data = new_data
            self.zone_combo.clear()
            self.zone_combo.addItems(list(new_data.keys()))
            QMessageBox.information(self, "Success", "Reference data updated.\nMissing values filled with averages.")
        else:
            QMessageBox.warning(self, "Warning", "No valid data to save.")
    
    def calculate_financials(self):
        if not self.selected_polygon:
            QMessageBox.warning(self, "Warning", "Please select an area on the map first!")
            return
            
        try:
            zone_type = self.zone_combo.currentText()
            deploy_type = self.deploy_combo.currentText()
            params = self.reference_data[zone_type]
            
            cost_per_meter = params['Cost_Per_Meter_Aerial'] if deploy_type == "Aerial" else params['Cost_Per_Meter_Trench']
            
            area_m2 = self.selected_area_m2
            display_area = self.distance_calc.convertAreaMeasurement(area_m2, self.area_unit)
            
            household_layer = self.household_combo.currentData()
            if household_layer:
                houses_passed = self.count_points_in_polygon(household_layer, self.selected_polygon)
            else:
                houses_passed = max(1, int(area_m2 / 1000))
            
            road_layer = self.road_combo.currentData()
            if road_layer:
                fiber_length = self.measure_lines_in_polygon(road_layer, self.selected_polygon)
            else:
                fiber_length = math.sqrt(area_m2) * 1.5
            
            houses_connected = houses_passed * params['Take_Rate_Initial']
            
            fiber_cost = fiber_length * cost_per_meter
            connection_cost = houses_connected * params['Capex_Per_Home_Connect']
            total_capex = fiber_cost + connection_cost
            
            annual_revenue = houses_connected * params['Avg_Monthly_ARPU'] * 12
            annual_opex = params['Opex_Fixed_Annual'] + (params['Backhaul_Cost_Monthly'] * 12)
            
            net_cash_flow = annual_revenue - annual_opex
            payback_period = total_capex / net_cash_flow if net_cash_flow > 0 else float('inf')
            
            cost_per_hp = total_capex / houses_passed if houses_passed > 0 else 0
            cost_per_meter_actual = fiber_cost / fiber_length if fiber_length > 0 else 0
            
            results = f"""
<h2>Fibre Deployment Financial Results</h2>
<h3>Configuration</h3>
Rurality Type: <b>{zone_type}</b><br>
Deployment Type: <b>{deploy_type}</b><br>
Take Rate: <b>{params['Take_Rate_Initial']*100:.1f}%</b>

<h3>Deployment Metrics</h3>
Houses Passed: <b>{houses_passed:,.0f}</b><br>
Houses Connected: <b>{int(houses_connected):,}</b><br>
Fibre Length: <b>{fiber_length:,.2f} m</b><br>
Area: <b>{display_area:,.2f} {self.area_unit_name}</b>

<h3>Financial Summary</h3>
Total CAPEX: <b>R {total_capex:,.2f}</b><br>
→ Fibre Cost: R {fiber_cost:,.2f}<br>
→ Connection Cost: R {connection_cost:,.2f}<br><br>

Annual Revenue: <b>R {annual_revenue:,.2f}</b><br>
Annual OPEX: <b>R {annual_opex:,.2f}</b><br>
Net Cash Flow: <b>R {net_cash_flow:,.2f}</b>

<h3>ROI Metrics</h3>
Payback Period: <b>{'Never (negative cash flow)' if payback_period == float('inf') else f'{payback_period:.2f} years'}</b><br>
Cost per House Passed: <b>R {cost_per_hp:,.2f}</b><br>
Cost per Meter: <b>R {cost_per_meter_actual:,.2f}</b>
"""
            self.results_text.setHtml(results)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Calculation failed:\n{str(e)}")
    
    def init_ui(self):
        self.setWindowTitle("Fibre Analyzer")  # ← Changed title
        self.setMinimumWidth(900)
        self.setMinimumHeight(800)
        
        layout = QVBoxLayout()
        
        # Reference Data Editor
        ref_group = QGroupBox("1. Edit Fibre Deployment Types")
        ref_layout = QVBoxLayout()
        self.ref_table = QTableWidget()
        self.ref_table.setColumnCount(8)
        self.ref_table.setHorizontalHeaderLabels([
            "Deployment Type", "Aerial R/m", "Trench R/m", "ARPU R/mo",
            "Take Rate", "Capex/Home", "Fixed Opex/yr", "Backhaul R/mo"
        ])
        self.update_ref_table()
        ref_layout.addWidget(self.ref_table)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add New Type")
        add_btn.clicked.connect(lambda: self.ref_table.insertRow(self.ref_table.rowCount()))
        btn_layout.addWidget(add_btn)
        
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.save_ref_changes)
        btn_layout.addWidget(save_btn)
        ref_layout.addLayout(btn_layout)
        ref_group.setLayout(ref_layout)
        layout.addWidget(ref_group)
        
        # Configuration
        config_group = QGroupBox("2. Configuration")
        config_layout = QVBoxLayout()
        
        zone_layout = QHBoxLayout()
        zone_layout.addWidget(QLabel("Type:"))
        self.zone_combo = QComboBox()
        self.zone_combo.addItems(list(self.reference_data.keys()))
        zone_layout.addWidget(self.zone_combo)
        config_layout.addLayout(zone_layout)
        
        deploy_layout = QHBoxLayout()
        deploy_layout.addWidget(QLabel("Method:"))
        self.deploy_combo = QComboBox()
        self.deploy_combo.addItems(["Aerial", "Trench"])
        deploy_layout.addWidget(self.deploy_combo)
        config_layout.addLayout(deploy_layout)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Area
        area_group = QGroupBox("3. Project Area")
        area_layout = QVBoxLayout()
        area_layout.addWidget(QLabel("Draw area polygon (left click points, right click finish)"))
        draw_btn = QPushButton("Start Drawing")
        draw_btn.clicked.connect(self.start_drawing)
        area_layout.addWidget(draw_btn)
        
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Display Unit:"))
        self.unit_combo = QComboBox()
        units = [
            ("m²", QgsUnitTypes.AreaSquareMeters),
            ("km²", QgsUnitTypes.AreaSquareKilometers),
            ("ha", QgsUnitTypes.AreaHectares),
            ("ac", QgsUnitTypes.AreaAcres),
            ("ft²", QgsUnitTypes.AreaSquareFeet),
            ("yd²", QgsUnitTypes.AreaSquareYards),
            ("mi²", QgsUnitTypes.AreaSquareMiles)
        ]
        for txt, val in units:
            self.unit_combo.addItem(txt, val)
        self.unit_combo.currentIndexChanged.connect(self.update_area_display)
        unit_layout.addWidget(self.unit_combo)
        area_layout.addLayout(unit_layout)
        
        self.area_status = QLabel("No area selected")
        self.area_status.setStyleSheet("color: gray; font-style: italic;")
        area_layout.addWidget(self.area_status)
        area_group.setLayout(area_layout)
        layout.addWidget(area_group)
        
        # Layers
        layer_group = QGroupBox("4. Optional Layers")
        layer_layout = QVBoxLayout()
        
        hh_layout = QHBoxLayout()
        hh_layout.addWidget(QLabel("Household Points:"))
        self.household_combo = QComboBox()
        self.populate_point_layers()
        hh_layout.addWidget(self.household_combo)
        layer_layout.addLayout(hh_layout)
        
        road_layout = QHBoxLayout()
        road_layout.addWidget(QLabel("Road/Fibre Lines:"))
        self.road_combo = QComboBox()
        self.populate_line_layers()
        road_layout.addWidget(self.road_combo)
        layer_layout.addLayout(road_layout)
        
        layer_group.setLayout(layer_layout)
        layout.addWidget(layer_group)
        
        # Calculate
        calc_btn = QPushButton("Calculate Financial Viability")
        calc_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 12px; }")
        calc_btn.clicked.connect(self.calculate_financials)
        layout.addWidget(calc_btn)
        
        # Results
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout()
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMinimumHeight(220)
        results_layout.addWidget(self.results_text)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        self.setLayout(layout)


def classFactory(iface):
    return FibreAnalyzer(iface)
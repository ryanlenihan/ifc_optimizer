import sys
import os
import traceback
from collections import OrderedDict
from pathlib import Path


from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QCheckBox,
    QFileDialog, QVBoxLayout, QHBoxLayout, QMessageBox, 
    QProgressDialog, QGroupBox, QGridLayout, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from src.optimizer import optimize_ifc

class OptimizerThread(QThread):
    finished = Signal(object, object, dict)  # (error, output_file, stats)
    
    def __init__(self, input_file, output_file, options):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.options = options

    def run(self):
        try:
            stats = optimize_ifc(self.input_file, self.output_file, self.options)
            self.finished.emit(None, self.output_file, stats)
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(str(e), self.output_file, {})

class IFCOptimizerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IFC Optimizer")
        self.setWindowIcon(QIcon("C:\\Codes\\ifc_optimizer\\axisverde.ico"))
        self.setMinimumWidth(600)

        # Define optimization options FIRST
        self.optimization_groups = OrderedDict({
            "Geometry / File size": {
                'remove_small_elements': ('Remove small elements (m³)', QLineEdit("0.001")),
                'lossy_rounding':        ('Round CartesianPoints (digits)', QLineEdit("2")),
                'deduplicate_geometry':  ('Deduplicate geometry', None),
                'merge_cartesian':       ('Merge duplicate CartesianPoints', None),
            },
            "Data clean-up": {
                'remove_metadata':            ('Remove metadata', None),
                'remove_empty_attributes':    ('Remove empty attributes', None),
                'remove_dash_props':          ('Remove “-” placeholder properties', None),
            },
            "Unused objects": {
                'remove_unused_spaces':          ('Remove unused spaces', None),
                'remove_unused_property_sets':   ('Remove unused property sets', None),
                'remove_unused_materials':       ('Remove unused materials', None),
                'remove_unused_classifications': ('Remove unused classifications', None),
                'remove_orphaned_entities':      ('Remove orphaned entities', None),
            },
            "De-duplication": {
                'dedupe_property_sets':     ('Merge duplicate PropertySets', None),
                'dedupe_classifications':   ('Merge duplicate Classifications', None),
            },
            "Output": {
                'ifczip_compress': ('Save IFCZIP copy', None),
                'flatten_spatial_structure': ('Flatten spatial structure', None),
            }
        })

        # Create UI components
        self.create_file_inputs()
        self.create_optimization_settings() 
        self.create_schema_conversion()  # Call ONCE here
        self.create_optimize_button()

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.input_group)
        main_layout.addWidget(self.output_group)
        main_layout.addWidget(self.settings_group)
        main_layout.addWidget(self.schema_group)
        main_layout.addLayout(self.button_layout)
        
        self.setLayout(main_layout)
        self.progress = None
        self.thread = None

    def create_schema_conversion(self):
        """Create schema conversion UI elements"""
        self.schema_group = QGroupBox("Schema Conversion")
        schema_layout = QHBoxLayout()
        self.convert_checkbox = QCheckBox("Convert to:")
        self.schema_combo = QComboBox()
        self.schema_combo.addItems(["IFC2X3", "IFC4"])
        schema_layout.addWidget(self.convert_checkbox)
        schema_layout.addWidget(self.schema_combo)
        self.schema_group.setLayout(schema_layout)
     
    # def create_optimization_settings(self):
        # """Create optimization checkboxes and parameters"""
        # self.settings_group = QGroupBox("Optimization Settings")
        # grid = QGridLayout()
        
        # self.checkboxes = {}
        # self.param_inputs = {}
        
        # row, col = 0, 0
        # for opt, (label, widget) in self.optimization_options.items():
            # cb = QCheckBox(label)
            # self.checkboxes[opt] = cb
            # grid.addWidget(cb, row, col)
            
            # if widget:
                # widget.setMaximumWidth(100)
                # self.param_inputs[opt] = widget
                # grid.addWidget(widget, row, col + 1)
                # col += 1
                
            # col += 1
            # if col >= 3:
                # col = 0
                # row += 1
                
        # self.settings_group.setLayout(grid)

    def run_optimizer(self):
        input_file = self.input_line.text()
        output_file = self.output_line.text()
        
        if not input_file or not output_file:
            QMessageBox.warning(self, "Missing Information", "Please select both input and output files.")
            return

        # Gather optimization parameters
        options = {
            opt: self.param_inputs[opt].text() if opt in self.param_inputs else True
            for opt, cb in self.checkboxes.items() if cb.isChecked()
        }
        
        # Add schema conversion options
        options.update({
            'convert_schema': self.convert_checkbox.isChecked(),
            'target_schema': self.schema_combo.currentText()
        })

        # Validate numerical parameters
        if 'remove_small_elements' in options:
            try:
                options['remove_small_elements'] = float(options['remove_small_elements'])
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for minimum volume.")
                return

        if 'lossy_rounding' in options:
            try:
                options['lossy_rounding'] = int(options['lossy_rounding'])
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter a whole number for CartesianPoint precision.")
                return

        # Remember for reporting below
        self._last_options = options
        self._last_output = output_file

        # Show progress dialog
        self.progress = QProgressDialog("Optimizing IFC file...", None, 0, 0, self)
        self.progress.setWindowTitle("Please Wait")
        self.progress.setMinimumDuration(0)
        self.progress.setWindowModality(Qt.ApplicationModal)
        self.progress.show()

        # Start optimization thread
        self.thread = OptimizerThread(input_file, output_file, options)
        self.thread.finished.connect(self.on_optimization_finished)
        self.thread.start()


    def create_file_inputs(self):
        """Create file input/output widgets"""
        # Input file section
        self.input_group = QGroupBox("Input File")
        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_browse = QPushButton("Browse")
        self.input_browse.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.input_browse)
        self.input_group.setLayout(input_layout)

        # Output file section
        self.output_group = QGroupBox("Output File")
        output_layout = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_browse = QPushButton("Browse")
        self.output_browse.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_line)
        output_layout.addWidget(self.output_browse)
        self.output_group.setLayout(output_layout)

    def create_optimization_settings(self):
        """Create group boxes for each optimisation category."""
        self.settings_group = QGroupBox("Optimisation Settings")
        vbox = QVBoxLayout()

        self.checkboxes = {}
        self.param_inputs = {}

        for title, opts in self.optimization_groups.items():
            grp = QGroupBox(title)
            grid = QGridLayout()
            row = col = 0
            for key, (label, widget) in opts.items():
                cb = QCheckBox(label)
                self.checkboxes[key] = cb
                grid.addWidget(cb, row, col)

                if widget:
                    widget.setMaximumWidth(80)
                    widget.setEnabled(False)
                    cb.toggled.connect(widget.setEnabled)   # enable when checked
                    self.param_inputs[key] = widget
                    grid.addWidget(widget, row, col + 1)
                    col += 1

                col += 1
                if col >= 4:   # four items per row looks tidy
                    col = 0
                    row += 1
            grp.setLayout(grid)
            vbox.addWidget(grp)

        self.settings_group.setLayout(vbox)


    def create_optimize_button(self):
        # Optimize button
        self.optimize_btn = QPushButton("Optimize")
        self.optimize_btn.setFixedSize(100, 32)
        self.optimize_btn.setStyleSheet("""
            QPushButton {
                background-color: #3da060;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #15597a; }
            QPushButton:pressed { background-color: #062433; }
        """)
        self.optimize_btn.clicked.connect(self.run_optimizer)
        
        # Button layout
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.optimize_btn)
        self.button_layout.addStretch(1)

    def browse_input(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select IFC file", "", "IFC Files (*.ifc);;All Files (*)"
        )
        if file_name:
            self.input_line.setText(file_name)
            base = os.path.basename(file_name)
            self.output_line.setText(os.path.join(os.path.dirname(file_name), f"optimized_{base}"))

    def browse_output(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Optimized IFC As", self.output_line.text() or "", "IFC Files (*.ifc);;All Files (*)"
        )
        if file_name:
            self.output_line.setText(file_name)

    # def run_optimizer(self):
        # input_file = self.input_line.text()
        # output_file = self.output_line.text()
        
        # if not input_file or not output_file:
            # QMessageBox.warning(self, "Missing Information", "Please select both input and output files.")
            # return

        # # Gather selected options and parameters
        # options = {
            # opt: self.param_inputs[opt].text() if opt in self.param_inputs else True
            # for opt, cb in self.checkboxes.items() if cb.isChecked()
        # }

        # # Validate numerical parameters
        # if 'remove_small_elements' in options:
            # try:
                # options['remove_small_elements'] = float(options['remove_small_elements'])
            # except ValueError:
                # QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for minimum volume.")
                # return

        # # Show progress dialog
        # self.progress = QProgressDialog("Optimizing IFC file...", None, 0, 0, self)
        # self.progress.setWindowTitle("Please Wait")
        # self.progress.setMinimumDuration(0)
        # self.progress.setWindowModality(Qt.ApplicationModal)
        # self.progress.show()

        # # Start optimization thread
        # self.thread = OptimizerThread(input_file, output_file, options)
        # self.thread.finished.connect(self.on_optimization_finished)
        # self.thread.start()

    def on_optimization_finished(self, error, output_file, stats):
        if self.progress:
            self.progress.close()
            self.progress.deleteLater()
        self.thread = None
        
        if error:
            QMessageBox.critical(self, "Error", f"An error occurred:\n{error}")
            return

        # Decide which file to report size on: .ifc or .ifczip
        out_path = output_file
        if getattr(self, "_last_options", {}).get("ifczip_compress", False):
            # assume .ifczip sits alongside the .ifc
            out_path = Path(output_file).with_suffix(".ifczip").as_posix()

        # Build stats message
        stats_text = "Optimization removed:\n"
        for key, value in stats.items():
            stats_text += f"- {value} {key.replace('_', ' ')}\n"
        
        # Get file sizes
        input_size = os.path.getsize(self.input_line.text()) / (1024 * 1024)
        output_size = os.path.getsize(out_path) / (1024 * 1024)
        reduction = input_size - output_size
        percentage = (1 - output_size / input_size) * 100
        
        message = (
            f"Optimized file saved to:\n{out_path}\n\n"
            f"Original size: {input_size:.2f} MB\n"
            f"Optimized size: {output_size:.2f} MB\n"
            f"Size reduction: {reduction:.2f} MB ({percentage:.2f}%)\n\n"
            f"{stats_text}"
        )
        
        QMessageBox.information(self, "Success", message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("C:\\Codes\\ifc_optimizer\\axisverde.ico"))
    window = IFCOptimizerGUI()
    window.show()
    sys.exit(app.exec())

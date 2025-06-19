"""Simple PySide6 front-end for :mod:`src.optimizer`."""

from __future__ import annotations

import os
import sys
import traceback
from collections import OrderedDict

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QCheckBox,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from src.optimizer import optimize_ifc

# Path to the application icon used in the GUI window.
APP_ICON = os.path.join(os.path.dirname(__file__), "axisverde.ico")

class OptimizerThread(QThread):
    """Worker thread that runs :func:`optimize_ifc` in the background."""

    finished = Signal(object, object, dict)  # (error, output_file, stats)
    
    def __init__(self, input_file: str, output_file: str, options: dict) -> None:
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.options = options

    def run(self) -> None:
        """Execute the optimization and emit the result."""
        try:
            stats = optimize_ifc(self.input_file, self.output_file, self.options)
            self.finished.emit(None, self.output_file, stats)
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(str(e), self.output_file, {})

class IFCOptimizerGUI(QWidget):
    """Main window allowing users to configure and run optimizations."""

    def __init__(self) -> None:
        """Construct and layout all widgets."""

        super().__init__()
        self.setWindowTitle("IFC Optimizer")
        self.setWindowIcon(QIcon(APP_ICON))
        self.setMinimumWidth(600)

        # Mapping of optimisation categories to their individual options.
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

    def create_schema_conversion(self) -> None:
        """Create controls for optional schema conversion."""
        self.schema_group = QGroupBox("Schema Conversion")
        schema_layout = QHBoxLayout()
        self.convert_checkbox = QCheckBox("Convert to:")
        self.schema_combo = QComboBox()
        self.schema_combo.addItems(["IFC2X3", "IFC4"])
        schema_layout.addWidget(self.convert_checkbox)
        schema_layout.addWidget(self.schema_combo)
        self.schema_group.setLayout(schema_layout)
     

    def run_optimizer(self) -> None:
        """Collect options and start the background optimization."""

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
                QMessageBox.warning(self, "Invalid Input",
                                    "Please enter a valid number for minimum volume.")
                return

        if 'lossy_rounding' in options:
            try:
                options['lossy_rounding'] = int(options['lossy_rounding'])
            except ValueError:
                QMessageBox.warning(self, "Invalid Input",
                                    "Please enter a whole number for CartesianPoint precision.")
                return


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

    def create_file_inputs(self) -> None:
        """Create widgets to choose the input and output files."""
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

    def create_optimization_settings(self) -> None:
        """Build the check boxes for all available optimisations."""
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


    def create_optimize_button(self) -> None:
        """Create the main 'Optimize' action button."""

        # Style and create the button
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

    def browse_input(self) -> None:
        """Prompt the user for an input file."""

        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select IFC file", "", "IFC Files (*.ifc);;All Files (*)"
        )
        if file_name:
            self.input_line.setText(file_name)
            base = os.path.basename(file_name)
            self.output_line.setText(
                os.path.join(os.path.dirname(file_name), f"optimized_{base}")
            )

    def browse_output(self) -> None:
        """Prompt the user for the output file path."""

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Optimized IFC As",
            self.output_line.text() or "",
            "IFC Files (*.ifc);;All Files (*)",
        )
        if file_name:
            self.output_line.setText(file_name)


    def on_optimization_finished(self, error: str | None, output_file: str, stats: dict) -> None:
        """Handle completion of the optimization thread."""
        if self.progress:
            self.progress.close()
            self.progress.deleteLater()
        self.thread = None
        
        if error:
            QMessageBox.critical(self, "Error", f"An error occurred:\n{error}")
        else:
            # Build stats message
            stats_text = "Optimization removed:\n"
            for key, value in stats.items():
                stats_text += f"- {value} {key.replace('_', ' ')}\n"
            
            # Get file sizes
            input_size = os.path.getsize(self.input_line.text()) / (1024 * 1024)
            output_size = os.path.getsize(output_file) / (1024 * 1024)
            reduction = input_size - output_size
            percentage = (1 - output_size/input_size) * 100
            
            message = (
                f"Optimized file saved to:\n{output_file}\n\n"
                f"Original size: {input_size:.2f} MB\n"
                f"Optimized size: {output_size:.2f} MB\n"
                f"Size reduction: {reduction:.2f} MB ({percentage:.2f}%)\n\n"
                f"{stats_text}"
            )
            
            QMessageBox.information(self, "Success", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(APP_ICON))
    window = IFCOptimizerGUI()
    window.show()
    sys.exit(app.exec())

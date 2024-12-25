import pygame
import dearpygui.dearpygui as dpg
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator
from qiskit.quantum_info import Statevector
import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import sys
import subprocess
import tempfile


@dataclass
class Wire:
    points: List[Tuple[int, int]]
    connected_gates: List[str] = None
    sensors: List[Tuple[int, int]] = None

    def __post_init__(self):
        self.connected_gates = []
        self.sensors = []


@dataclass
class Gate:
    type: str
    pos: Tuple[int, int]
    connected_wires: List[Wire] = None

    def __post_init__(self):
        self.connected_wires = []


class QuantumCircuitDesigner:
    def __init__(self):
        pygame.init()

        self.BACKGROUND = (15, 15, 20)
        self.GRID_COLOR = (30, 30, 40)
        self.TEXT_COLOR = (200, 200, 220)
        self.WIRE_COLOR = (100, 200, 255)
        self.SENSOR_COLOR = (255, 100, 100)
        self.GATE_COLORS = {
            "H": (100, 149, 237),
            "X": (255, 127, 80),
            "Y": (147, 112, 219),
            "Z": (102, 205, 170),
            "CNOT": (255, 165, 0),
            "SENSOR": (255, 50, 50),
        }

        self.screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        pygame.display.set_caption("Quantum Circuit Designer")

        self.offset_x = 0
        self.offset_y = 0
        self.grid_size = 20
        self.zoom = 1.0

        self.wires = []
        self.gates = []
        self.sensors = []
        self.circuit = None
        self.simulator = AerSimulator()

        self.drawing_wire = False
        self.current_wire_points = []
        self.dragging_gate = None
        self.selected_tool = None
        self.sensor_data = {}
        self.sensor_table = None

        self.font = pygame.font.SysFont("Arial", 16)

        dpg.create_context()
        self.setup_dpg()

    def setup_dpg(self):
        dpg.create_viewport(title="Circuit Tools", width=300, height=600)

        with dpg.window(label="Tools", width=300, height=600):
            with dpg.tab_bar():
                with dpg.tab(label="Tools"):
                    with dpg.group():
                        dpg.add_text("Gates")
                        for gate in self.GATE_COLORS:
                            if gate != "SENSOR":
                                button = dpg.add_button(
                                    label=gate,
                                    callback=lambda s, a, u: self.select_tool(u),
                                    user_data=gate,
                                )
                                tooltip_text = {
                                    "H": "Hadamard Gate - Creates quantum superposition",
                                    "X": "Pauli-X Gate - Quantum NOT gate",
                                    "Y": "Pauli-Y Gate - Rotation around Y-axis",
                                    "Z": "Pauli-Z Gate - Phase flip",
                                    "CNOT": "Controlled-NOT Gate - Two-qubit gate",
                                }[gate]
                                with dpg.tooltip(parent=button):
                                    dpg.add_text(tooltip_text)

                        dpg.add_separator()
                        dpg.add_text("Tools")

                        wire_btn = dpg.add_button(
                            label="Draw Wire", callback=lambda: self.select_tool("WIRE")
                        )
                        with dpg.tooltip(parent=wire_btn):
                            dpg.add_text("Click and drag to create quantum wires")

                        delete_btn = dpg.add_button(
                            label="Delete", callback=lambda: self.select_tool("DELETE")
                        )
                        with dpg.tooltip(parent=delete_btn):
                            dpg.add_text("Click to remove gates, wires, or sensors")

                        clear_btn = dpg.add_button(
                            label="Clear All", callback=self.clear_board
                        )
                        with dpg.tooltip(parent=clear_btn):
                            dpg.add_text("Reset the entire circuit")

                        sim_btn = dpg.add_button(
                            label="Simulate", callback=self.simulate_circuit
                        )
                        with dpg.tooltip(parent=sim_btn):
                            dpg.add_text(
                                "Run quantum simulation and collect measurements"
                            )

                        dpg.add_separator()
                        with dpg.collapsing_header(
                            label="Circuit Info", default_open=True
                        ):
                            self.circuit_info = dpg.add_text("No circuit simulated yet")

                        with dpg.collapsing_header(
                            label="Sensor Data", default_open=True
                        ):
                            self.sensor_text = dpg.add_text("No measurements yet")

                with dpg.tab(label="Help"):
                    dpg.add_text("Quantum Circuit Designer Help", color=(255, 255, 0))
                    dpg.add_separator()

                    dpg.add_text("Gates:", color=(150, 255, 150))
                    dpg.add_text("H - Hadamard Gate (Creates superposition)")
                    dpg.add_text("X - Pauli-X Gate (NOT gate)")
                    dpg.add_text("Y - Pauli-Y Gate")
                    dpg.add_text("Z - Pauli-Z Gate")
                    dpg.add_text("CNOT - Controlled-NOT Gate")

                    dpg.add_separator()
                    dpg.add_text("Tools:", color=(150, 255, 150))
                    dpg.add_text("Draw Wire - Click and drag to create wires")
                    dpg.add_text("Delete - Remove components")
                    dpg.add_text("Clear All - Reset the circuit")
                    dpg.add_text("Simulate - Run quantum simulation")

                    dpg.add_separator()
                    dpg.add_text("Tips:", color=(150, 255, 150))
                    dpg.add_text("- Gates snap to wires automatically")
                    dpg.add_text("- Right-click to add sensors")
                    dpg.add_text("- Sensors measure quantum states")

        dpg.setup_dearpygui()
        dpg.show_viewport()

    def initialize_circuit(self):
        if not self.wires:
            return

        try:
            qr = QuantumRegister(max(len(self.wires), 1))
            cr = ClassicalRegister(max(len(self.wires), 1))
            self.circuit = QuantumCircuit(qr, cr)
            print(f"Circuit initialized with {len(self.wires)} wires")

        except Exception as e:
            print(f"Circuit initialization error: {str(e)}")

    def snap_to_grid(self, pos):
        x = round(pos[0] / self.grid_size) * self.grid_size
        y = round(pos[1] / self.grid_size) * self.grid_size
        return (x, y)

    def handle_mouse_down(self, pos):
        grid_pos = self.snap_to_grid(pos)

        if self.selected_tool == "DELETE":
            for gate in self.gates[:]:
                if self.point_near_pos(gate.pos, grid_pos):
                    self.gates.remove(gate)

            for sensor in self.sensors[:]:
                if self.point_near_pos(sensor, grid_pos):
                    self.sensors.remove(sensor)

            for wire in self.wires[:]:
                for p1, p2 in zip(wire.points, wire.points[1:]):
                    if self.point_on_line_segment(grid_pos, p1, p2):
                        self.wires.remove(wire)
                        break
        elif self.selected_tool == "WIRE":
            self.drawing_wire = True
            self.current_wire_points = [grid_pos]
        elif self.selected_tool in self.GATE_COLORS:
            self.gates.append(Gate(self.selected_tool, grid_pos))
        elif self.selected_tool == "SENSOR":
            self.sensors.append(grid_pos)

    def handle_mouse_up(self, pos):
        if self.drawing_wire:
            self.drawing_wire = False
            if len(self.current_wire_points) > 1:
                self.wires.append(Wire(self.current_wire_points.copy()))
            self.current_wire_points = []

    def handle_mouse_motion(self, pos):
        if self.drawing_wire:
            grid_pos = self.snap_to_grid(pos)
            if grid_pos != self.current_wire_points[-1]:
                self.current_wire_points.append(grid_pos)

    def draw_wire(self, points, color=None):
        if not color:
            color = self.WIRE_COLOR
        if len(points) > 1:
            pygame.draw.lines(self.screen, color, False, points, 2)

    def draw_gate(self, gate: Gate):
        color = self.GATE_COLORS[gate.type]
        size = 20
        rect = pygame.Rect(gate.pos[0] - size // 2, gate.pos[1] - size // 2, size, size)
        pygame.draw.rect(self.screen, color, rect, border_radius=3)

        label_map = {"H": "H", "X": "X", "Y": "Y", "Z": "Z", "CNOT": "C", "SENSOR": "S"}

        text = self.font.render(label_map[gate.type], True, (0, 0, 0))
        text_rect = text.get_rect(center=gate.pos)
        self.screen.blit(text, text_rect)

    def draw_sensor(self, pos):
        size = 20
        rect = pygame.Rect(pos[0] - size // 2, pos[1] - size // 2, size, size)
        pygame.draw.rect(self.screen, self.SENSOR_COLOR, rect, border_radius=3)

        text = self.font.render("S", True, (0, 0, 0))
        text_rect = text.get_rect(center=pos)
        self.screen.blit(text, text_rect)

    def draw(self):
        self.screen.fill(self.BACKGROUND)

        w, h = self.screen.get_size()
        for x in range(0, w, self.grid_size):
            pygame.draw.line(self.screen, self.GRID_COLOR, (x, 0), (x, h))
        for y in range(0, h, self.grid_size):
            pygame.draw.line(self.screen, self.GRID_COLOR, (0, y), (w, y))

        for wire in self.wires:
            self.draw_wire(wire.points)
        if self.drawing_wire:
            self.draw_wire(self.current_wire_points, (255, 255, 0))

        for gate in self.gates:
            self.draw_gate(gate)

        for sensor in self.sensors:
            self.draw_sensor(sensor)

    def simulate_circuit(self):
        if not self.wires:
            print("No wires to simulate")
            return

        try:
            self.initialize_circuit()

            wire_connections = self.find_wire_connections()
            print(f"Wire connections: {wire_connections}")

            processed_wires = set()
            for wire_idx, wire in enumerate(self.wires):
                if wire_idx in processed_wires:
                    continue

                connected_group = self.get_connected_wires(wire_idx, wire_connections)
                print(f"Processing connected wire group: {connected_group}")

                for connected_wire_idx in connected_group:
                    self.circuit.reset(connected_wire_idx)
                    wire = self.wires[connected_wire_idx]

                    wire_gates = []
                    for gate in self.gates:
                        for p1, p2 in zip(wire.points, wire.points[1:]):
                            if self.point_on_line_segment(gate.pos, p1, p2):
                                wire_gates.append(
                                    (gate, self.get_position_along_wire(gate.pos, wire))
                                )

                    wire_gates.sort(key=lambda x: x[1])

                    for gate, _ in wire_gates:
                        self.add_gate_to_circuit(gate.type, connected_wire_idx)

                    processed_wires.add(connected_wire_idx)

            measurements_added = False
            for sensor_idx, sensor_pos in enumerate(self.sensors):
                for wire_idx, wire in enumerate(self.wires):
                    for p1, p2 in zip(wire.points, wire.points[1:]):
                        if self.point_on_line_segment(sensor_pos, p1, p2):
                            self.circuit.measure(wire_idx, wire_idx)
                            measurements_added = True
                            break

            if not measurements_added:
                self.circuit.measure_all()

            print("Final circuit:")
            print(self.circuit)

            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.write(str(self.circuit))
                temp_path = f.name

            if sys.platform == "darwin":
                subprocess.Popen(
                    [
                        "osascript",
                        "-e",
                        f'tell app "Terminal" to do script "less {temp_path}"',
                    ]
                )
            elif sys.platform == "linux":
                subprocess.Popen(["gnome-terminal", "--", "less", temp_path])
            elif sys.platform == "win32":
                subprocess.Popen(
                    ["start", "cmd", "/k", f"type {temp_path}"], shell=True
                )

            circuit_str = str(self.circuit).split("\n")
            simplified_circuit = []
            for line in circuit_str:
                simplified_line = (
                    line.replace("─", "-")
                    .replace("│", "|")
                    .replace("┌", "+")
                    .replace("┐", "+")
                    .replace("└", "+")
                    .replace("┘", "+")
                    .replace("├", "+")
                    .replace("┤", "+")
                    .replace("╭", "(")
                    .replace("╰", ")")
                    .replace("═", "=")
                    .replace("║", "|")
                    .replace("╬", "|")
                    .replace("░", "/")
                    .replace("╩", "|")
                    .replace("╥", "-")
                    .replace("■", "%")
                )
                simplified_circuit.append(simplified_line)

            dpg.set_value(self.circuit_info, "\n".join(simplified_circuit))

            job = self.simulator.run(self.circuit, shots=1000)
            counts = job.result().get_counts()
            print(f"Raw counts: {counts}")

            self.sensor_data = self.process_measurement_results(counts)
            print(f"Processed data: {self.sensor_data}")
            self.update_sensor_table()

        except Exception as e:
            error_msg = f"Simulation error: {str(e)}"
            print(error_msg)
            dpg.set_value(self.circuit_info, error_msg)
            import traceback

            traceback.print_exc()

    def find_wire_connections(self):
        connections = {}

        for i, wire1 in enumerate(self.wires):
            connections[i] = set()
            for j, wire2 in enumerate(self.wires):
                if i != j:
                    for p1 in [wire1.points[0], wire1.points[-1]]:
                        for p2 in [wire2.points[0], wire2.points[-1]]:
                            if self.point_near_pos(p1, p2, threshold=10):
                                connections[i].add(j)

        return connections

    def get_connected_wires(self, start_wire, connections):
        connected = set([start_wire])
        stack = [start_wire]

        while stack:
            current = stack.pop()
            for neighbor in connections[current]:
                if neighbor not in connected:
                    connected.add(neighbor)
                    stack.append(neighbor)

        return connected

    def process_measurement_results(self, counts):
        processed_data = {}
        total_shots = sum(counts.values())

        print(f"Processing measurements: {counts}")

        if not counts or total_shots == 0:
            return {}

        for bitstring, count in counts.items():
            probability = count / total_shots
            bits = "".join(bitstring.split())

            for sensor_idx, bit in enumerate(bits):
                sensor_key = f"Sensor {sensor_idx}"
                if sensor_key not in processed_data:
                    processed_data[sensor_key] = {"0": 0, "1": 0}
                if bit in ["0", "1"]:
                    processed_data[sensor_key][bit] += probability

        print(f"Processed data: {processed_data}")
        return processed_data

    def point_on_line_segment(self, point, line_start, line_end):
        d = self.point_to_line_distance(point, line_start, line_end)
        if d > self.grid_size / 2:
            return False

        x, y = point
        x1, y1 = line_start
        x2, y2 = line_end

        return min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)

    def get_position_along_wire(self, point, wire):
        total_length = 0
        current_length = 0
        target_segment = None
        segment_start = 0

        for p1, p2 in zip(wire.points, wire.points[1:]):
            segment_length = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
            total_length += segment_length

            if self.point_on_line_segment(point, p1, p2):
                target_segment = (p1, p2)
                segment_start = current_length
            current_length += segment_length

        if target_segment:
            p1, p2 = target_segment
            segment_length = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
            point_distance = math.sqrt(
                (point[0] - p1[0]) ** 2 + (point[1] - p1[1]) ** 2
            )
            return (segment_start + point_distance) / total_length

        return 0

    def update_sensor_table(self):
        if not self.sensor_data:
            dpg.set_value(self.sensor_text, "No measurements available")
            return

        result_text = []
        result_text.append("Measurement Results:")
        result_text.append("-" * 20)

        for sensor_key, measurements in self.sensor_data.items():
            result_text.append(f"\n{sensor_key}:")
            result_text.append(f"State |0>: {measurements['0']:.3f}")
            result_text.append(f"State |1>: {measurements['1']:.3f}")

            prob_0 = measurements["0"]
            if prob_0 > 0.9:
                interpretation = "Definite 0 state"
            elif prob_0 < 0.1:
                interpretation = "Definite 1 state"
            elif 0.4 <= prob_0 <= 0.6:
                interpretation = "Superposition state"
            else:
                interpretation = "Mixed state"
            result_text.append(f"Analysis: {interpretation}")
            result_text.append("-" * 20)

        dpg.set_value(self.sensor_text, "\n".join(result_text))

    def run(self):
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_mouse_down(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.handle_mouse_up(event.pos)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event.pos)
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )

            self.draw()
            pygame.display.flip()
            dpg.render_dearpygui_frame()
            clock.tick(60)

        dpg.destroy_context()
        pygame.quit()

    def select_tool(self, tool):
        self.selected_tool = tool
        print(f"Selected tool: {tool}")

        self.drawing_wire = False
        self.current_wire_points = []
        self.dragging_gate = None

    def find_nearest_wire_index(self, point) -> Optional[int]:
        min_dist = float("inf")
        nearest_idx = None

        for idx, wire in enumerate(self.wires):
            for p1, p2 in zip(wire.points, wire.points[1:]):
                dist = self.point_to_line_distance(point, p1, p2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = idx

        return nearest_idx if min_dist < self.grid_size else None

    def add_gate_to_circuit(self, gate_type: str, wire_idx: int):
        if not self.circuit or wire_idx is None:
            return

        try:
            if gate_type == "H":
                self.circuit.h(wire_idx)
                print(f"Added Hadamard gate to wire {wire_idx}")
            elif gate_type == "X":
                self.circuit.x(wire_idx)
            elif gate_type == "Y":
                self.circuit.y(wire_idx)
            elif gate_type == "Z":
                self.circuit.z(wire_idx)
            elif gate_type == "CNOT" and wire_idx < len(self.wires) - 1:
                self.circuit.cx(wire_idx, wire_idx + 1)
        except Exception as e:
            print(f"Error adding gate: {str(e)}")

    def point_to_line_distance(self, point, line_start, line_end):
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end

        if (x1, y1) == (x2, y2):
            return math.sqrt((x0 - x1) ** 2 + (y0 - y1) ** 2)

        numerator = (x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)
        denominator = math.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)

        if denominator == 0:
            return float("inf")

        t = max(
            0,
            min(1, numerator / (denominator**2)),
        )

        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)

        return math.sqrt((x0 - proj_x) ** 2 + (y0 - proj_y) ** 2)

    def clear_board(self):
        self.wires = []
        self.gates = []
        self.sensors = []
        self.circuit = None
        self.sensor_data = {}
        self.update_sensor_table()

    def point_near_pos(self, pos1, pos2, threshold=20):
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        return (dx * dx + dy * dy) <= threshold * threshold


if __name__ == "__main__":
    app = QuantumCircuitDesigner()
    app.run()

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import datetime
import calendar

# Setup path to ensure local imports work
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import db_manager
import scheduler_opt

def get_default_dates():
    """Returns the start and end date string of the current month."""
    today = datetime.date.today()
    # If it's June 2026, let's find June 1st to June 30th
    first_day = today.replace(day=1)
    last_day_num = calendar.monthrange(today.year, today.month)[1]
    last_day = today.replace(day=last_day_num)
    return first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")

def parse_args():
    default_start, default_end = get_default_dates()
    
    parser = argparse.ArgumentParser(
        description="Banquillo pipeline: Automatiza la importación, optimización de horarios y exportación a Excel."
    )
    
    parser.add_argument(
        "--import-path",
        type=str,
        default=os.path.join(BASE_DIR, "AGENDAS - LA CUMBRE.xlsx"),
        help="Ruta del archivo Excel de origen para importar (por defecto: AGENDAS - LA CUMBRE.xlsx)"
    )
    parser.add_argument(
        "--export-path",
        type=str,
        default=os.path.join(BASE_DIR, "AGENDAS_EXPORTED.xlsx"),
        help="Ruta del archivo Excel de salida para exportar (por defecto: AGENDAS_EXPORTED.xlsx)"
    )
    parser.add_argument(
        "--barrio",
        type=str,
        default="La Cumbre",
        help="Barrio/comunidad a optimizar (por defecto: La Cumbre)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=default_start,
        help=f"Fecha de inicio del periodo YYYY-MM-DD (por defecto: {default_start})"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=default_end,
        help=f"Fecha de fin del periodo YYYY-MM-DD (por defecto: {default_end})"
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=100,
        help="Tamaño de la población para el algoritmo genético (por defecto: 100)"
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=200,
        help="Número de generaciones para el algoritmo genético (por defecto: 200)"
    )
    parser.add_argument(
        "--mut-rate",
        type=float,
        default=0.15,
        help="Tasa de mutación (por defecto: 0.15)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=db_manager.DEFAULT_DB_PATH,
        help="Ruta del archivo de base de datos SQLite"
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
        help="No importar datos desde el Excel de origen; usar el estado actual de la base de datos"
    )
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Configure stdout to use utf-8 if possible to prevent encoding errors on Windows
    try:
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

    print("=" * 60)
    print("INICIANDO PIPELINE DE AUTOMATIZACION DE HORARIOS - BANQUILLO")
    print("=" * 60)
    print(f"Base de datos:       {args.db_path}")
    print(f"Barrio a optimizar:  {args.barrio}")
    print(f"Rango de fechas:     {args.start_date} a {args.end_date}")
    print(f"Configuracion AG:    Poblacion={args.pop_size}, Generaciones={args.generations}, Mutacion={args.mut_rate}")
    print("-" * 60)

    # 1. Importacion
    if not args.no_import:
        if not os.path.exists(args.import_path):
            print(f"Error: El archivo Excel de importacion no existe: {args.import_path}")
            sys.exit(1)
        print(f"1/3 Importando datos desde: {args.import_path} ...")
        try:
            db_manager.import_from_excel(args.import_path, db_path=args.db_path, reset=True)
            print("Datos importados e inicializados con exito.")
        except Exception as e:
            print(f"Error en la fase de importacion: {e}")
            sys.exit(1)
    else:
        print("1/3 Fase de importacion omitida (--no-import).")

    print("-" * 60)

    # 2. Optimizacion
    print("2/3 Ejecutando optimizacion por Algoritmo Genetico...")
    try:
        res = scheduler_opt.optimizar_horarios(
            barrio=args.barrio,
            fecha_inicio=args.start_date,
            fecha_fin=args.end_date,
            db_path=args.db_path,
            pop_size=args.pop_size,
            generations=args.generations,
            mutation_rate=args.mut_rate
        )
        
        if res:
            analysis = res['analysis']
            print("Optimizacion completada de manera exitosa.")
            print("\nMetricas de la Agenda Optimizada:")
            print(f"  - Total de slots a cubrir:      {analysis['total_slots']}")
            print(f"  - Slots asignados con exito:    {analysis['assigned_slots']}")
            print(f"  - Slots que quedaron vacios:     {analysis['empty_slots']}")
            print(f"  - Cobertura de turnos lograda:   {analysis['cobertura_pct']:.2f}%")
            print(f"  - Penalizacion total (Fitness):  {res['fitness']:.2f}")
            print(f"  - Traslapes de orientadores:     {analysis['overlaps']}")
            print(f"  - Asignaciones invalidas:        {analysis['invalid_availabilities']}")
            print(f"  - Desviacion estandar de horas:  {analysis['std_dev_horas']:.2f} horas")
        else:
            print("No se encontraron turnos requeridos o no se pudo optimizar el periodo.")
    except Exception as e:
        print(f"Error en la fase de optimizacion: {e}")
        sys.exit(1)

    print("-" * 60)

    # 3. Exportacion
    print(f"3/3 Exportando agenda optimizada a: {args.export_path} ...")
    try:
        db_manager.export_to_excel(args.export_path, db_path=args.db_path)
        print("Archivo Excel generado y formateado exitosamente.")
    except Exception as e:
        print(f"Error en la fase de exportacion: {e}")
        sys.exit(1)

    print("=" * 60)
    print("PIPELINE COMPLETADO SATISFACTORIAMENTE")
    print("=" * 60)

if __name__ == "__main__":
    main()

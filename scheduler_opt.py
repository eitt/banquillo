import sys
import os
import random
import datetime
import sqlite3

# Ensure Banquillo directory is in path for db_manager import
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import db_manager

def parse_date(d):
    """Parses a date string or object to a datetime.date object."""
    if isinstance(d, datetime.date):
        return d
    if isinstance(d, datetime.datetime):
        return d.date()
    return datetime.date.fromisoformat(str(d).strip())

def row_to_dict(row):
    """Converts a SQLite row or similar object to a standard Python dictionary."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except (ValueError, TypeError):
        if hasattr(row, 'keys'):
            return {k: row[k] for k in row.keys()}
        return row

def check_availability(orientador_id, fecha, hora_inicio, hora_fin, availabilities_by_orientador):
    """Checks if an orientador is available during the given date and time range."""
    # fecha is a datetime.date object
    if orientador_id not in availabilities_by_orientador:
        return False
    date_availabilities = availabilities_by_orientador[orientador_id].get(fecha, [])
    for d_start, d_end in date_availabilities:
        # An availability slot covers the turno slot if it starts at or before and ends at or after
        if d_start <= hora_inicio and d_end >= hora_fin:
            return True
    return False

def calcular_fitness(individual, slots, availabilities_by_orientador, max_horas_semanales, active_orientadores):
    """Calculates the fitness score (total penalty) for a given individual.
    Lower score is better."""
    penalizacion = 0.0
    
    # Track hours per week and total hours per orientador
    horas_por_semana_orientador = {}  # (orientador_id, week_key) -> hours
    horas_totales_orientador = {o: 0.0 for o in active_orientadores}
    
    # Group intervals by orientador to check for overlaps
    slots_por_orientador = {}
    
    for i, orientador_id in enumerate(individual):
        if orientador_id is None:
            # H4: Empty slot penalty
            penalizacion += 1000
            continue
            
        if orientador_id not in horas_totales_orientador:
            horas_totales_orientador[orientador_id] = 0.0
            
        slot = slots[i]
        fecha = slot['fecha']
        hora_inicio = slot['hora_inicio']
        hora_fin = slot['hora_fin']
        
        # Calculate duration of the slot in hours
        try:
            h_start, m_start = map(int, hora_inicio.split(':'))
            h_end, m_end = map(int, hora_fin.split(':'))
            duracion = (h_end * 60 + m_end - (h_start * 60 + m_start)) / 60.0
        except Exception:
            duracion = 1.0  # default fallback
            
        horas_totales_orientador[orientador_id] += duracion
        
        # Calculate week key using isocalendar()
        try:
            date_obj = parse_date(fecha)
            year, week, weekday = date_obj.isocalendar()
            week_key = (year, week)
        except Exception:
            week_key = (2025, 1)  # default fallback
            
        key_weekly = (orientador_id, week_key)
        horas_por_semana_orientador[key_weekly] = horas_por_semana_orientador.get(key_weekly, 0.0) + duracion
        
        # H1: Availability check
        slot_fecha = parse_date(fecha)
        if not check_availability(orientador_id, slot_fecha, hora_inicio, hora_fin, availabilities_by_orientador):
            penalizacion += 10000
            
        # Collect intervals to check for overlaps
        if orientador_id not in slots_por_orientador:
            slots_por_orientador[orientador_id] = []
        slots_por_orientador[orientador_id].append((fecha, hora_inicio, hora_fin))
        
    # H2: Overlap check
    for orientador_id, intervals in slots_por_orientador.items():
        n = len(intervals)
        for idx1 in range(n):
            f1, s1, e1 = intervals[idx1]
            for idx2 in range(idx1 + 1, n):
                f2, s2, e2 = intervals[idx2]
                if f1 == f2:
                    # Overlap if max(start1, start2) < min(end1, end2)
                    if max(s1, s2) < min(e1, e2):
                        penalizacion += 10000
                        
    # H3: Max weekly hours check
    for (orientador_id, week_key), total_hours in horas_por_semana_orientador.items():
        max_h = max_horas_semanales.get(orientador_id, 40)
        if total_hours > max_h:
            exceeded = total_hours - max_h
            penalizacion += exceeded * 5000
            
    # S1: Workload balance (standard deviation of total hours assigned)
    if len(active_orientadores) > 1:
        hours_list = [horas_totales_orientador[o] for o in active_orientadores]
        mean_hours = sum(hours_list) / len(hours_list)
        variance = sum((h - mean_hours) ** 2 for h in hours_list) / len(hours_list)
        std_dev = variance ** 0.5
        penalizacion += std_dev * 100.0  # Weight of 100 for soft constraint
        
    return penalizacion

def crossover(parent1, parent2, slots):
    """Uniform crossover operation that respects committed slots."""
    child1 = []
    child2 = []
    for i, (g1, g2) in enumerate(zip(parent1, parent2)):
        if slots[i]['committed']:
            child1.append(slots[i]['fixed_orientador_id'])
            child2.append(slots[i]['fixed_orientador_id'])
        else:
            if random.random() < 0.5:
                child1.append(g1)
                child2.append(g2)
            else:
                child1.append(g2)
                child2.append(g1)
    return child1, child2

def mutate(individual, slot_candidates, slots, mutation_rate):
    """Intelligent mutation operation that respects committed slots
    and prefers candidates who are available for that slot."""
    new_ind = list(individual)
    for i in range(len(new_ind)):
        if slots[i]['committed']:
            new_ind[i] = slots[i]['fixed_orientador_id']
            continue
        if random.random() < mutation_rate:
            candidates = slot_candidates[i]
            if candidates:
                new_ind[i] = random.choice(candidates + [None])
            else:
                new_ind[i] = None
    return new_ind

def tournament_selection(population, fitnesses, k=3):
    """Selects an individual using tournament selection."""
    selected_indices = random.sample(range(len(population)), k)
    best_idx = min(selected_indices, key=lambda idx: fitnesses[idx])
    return population[best_idx]

def limpiar_asignaciones_no_comprometidas(barrio, fecha_inicio, fecha_fin, db_path):
    """Deletes existing assignments and free appointments in the range that are not booked/committed."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    committed_ids = []
    try:
        # Find assignments that are committed (have appointments with status != 'libre')
        committed_query = """
        SELECT DISTINCT a.id
        FROM asignaciones a
        JOIN turnos_requeridos t ON a.turno_id = t.id
        JOIN citas c ON c.asignacion_id = a.id
        WHERE t.barrio = ? AND t.fecha >= ? AND t.fecha <= ? AND c.estado != 'libre'
        """
        cursor.execute(committed_query, (barrio, fecha_inicio, fecha_fin))
        committed_ids = [row[0] for row in cursor.fetchall()]
        
        # Find all assignments in this range
        all_query = """
        SELECT a.id
        FROM asignaciones a
        JOIN turnos_requeridos t ON a.turno_id = t.id
        WHERE t.barrio = ? AND t.fecha >= ? AND t.fecha <= ?
        """
        cursor.execute(all_query, (barrio, fecha_inicio, fecha_fin))
        all_assignments = [row[0] for row in cursor.fetchall()]
        
        to_delete_assign_ids = [assign_id for assign_id in all_assignments if assign_id not in committed_ids]
                
        if to_delete_assign_ids:
            placeholders = ",".join("?" for _ in to_delete_assign_ids)
            # Delete corresponding appointments
            cursor.execute(f"DELETE FROM citas WHERE asignacion_id IN ({placeholders})", to_delete_assign_ids)
            # Delete assignments
            cursor.execute(f"DELETE FROM asignaciones WHERE id IN ({placeholders})", to_delete_assign_ids)
            
        conn.commit()
        print(f"Limpieza: Se eliminaron {len(to_delete_assign_ids)} asignaciones no comprometidas.")
    except Exception as e:
        conn.rollback()
        print("Error al limpiar asignaciones previas:", e)
    finally:
        conn.close()

def obtener_asignaciones_comprometidas(barrio, fecha_inicio, fecha_fin, db_path):
    """Retrieves committed assignments to preserve them."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    committed = []
    try:
        query = """
        SELECT a.turno_id, a.orientador_id
        FROM asignaciones a
        JOIN turnos_requeridos t ON a.turno_id = t.id
        JOIN citas c ON c.asignacion_id = a.id
        WHERE t.barrio = ? AND t.fecha >= ? AND t.fecha <= ? AND c.estado != 'libre'
        """
        cursor.execute(query, (barrio, fecha_inicio, fecha_fin))
        committed = cursor.fetchall()
    except Exception as e:
        print("Error al obtener asignaciones comprometidas:", e)
    finally:
        conn.close()
    return committed

def guardar_asignaciones(individual, slots, db_path):
    """Persists the optimized assignments into the database using db_manager."""
    saved_count = 0
    for i, orientador_id in enumerate(individual):
        slot = slots[i]
        if slot['committed']:
            # Already in DB and preserved
            continue
        if orientador_id is not None:
            try:
                # Create assignment
                assign_id = db_manager.create_asignacion(
                    turno_id=slot['turno_id'],
                    orientador_id=orientador_id,
                    estado='asignado',
                    db_path=db_path
                )
                # Create appointment (cita) with state 'libre'
                db_manager.create_cita(
                    asignacion_id=assign_id,
                    nombre_usuario=None,
                    contacto_usuario=None,
                    estado='libre',
                    db_path=db_path
                )
                saved_count += 1
            except Exception as e:
                print(f"Error al guardar asignacion/cita para turno {slot['turno_id']}, orientador {orientador_id}: {e}")
    print(f"Guardado exitoso: {saved_count} nuevas asignaciones insertadas.")

def analizar_resultado(individual, slots, availabilities_by_orientador, max_horas_semanales, active_orientadores):
    """Calculates detailed metrics for the best individual schedule."""
    total_slots = len(slots)
    assigned_slots = 0
    empty_slots = 0
    invalid_availabilities = 0
    overlaps = 0
    exceeded_weekly_hours = {}
    
    horas_por_semana_orientador = {}
    horas_totales_orientador = {o: 0.0 for o in active_orientadores}
    slots_por_orientador = {}
    
    for i, orientador_id in enumerate(individual):
        if orientador_id is None:
            empty_slots += 1
            continue
            
        assigned_slots += 1
        slot = slots[i]
        
        if orientador_id not in horas_totales_orientador:
            horas_totales_orientador[orientador_id] = 0.0
            
        fecha = slot['fecha']
        hora_inicio = slot['hora_inicio']
        hora_fin = slot['hora_fin']
        
        try:
            h_start, m_start = map(int, hora_inicio.split(':'))
            h_end, m_end = map(int, hora_fin.split(':'))
            duracion = (h_end * 60 + m_end - (h_start * 60 + m_start)) / 60.0
        except Exception:
            duracion = 1.0
            
        horas_totales_orientador[orientador_id] += duracion
        
        try:
            date_obj = parse_date(fecha)
            year, week, weekday = date_obj.isocalendar()
            week_key = (year, week)
        except Exception:
            week_key = (2025, 1)
            
        key_weekly = (orientador_id, week_key)
        horas_por_semana_orientador[key_weekly] = horas_por_semana_orientador.get(key_weekly, 0.0) + duracion
        
        # Availability
        slot_fecha = parse_date(fecha)
        if not check_availability(orientador_id, slot_fecha, hora_inicio, hora_fin, availabilities_by_orientador):
            invalid_availabilities += 1
            
        # Overlaps collection
        if orientador_id not in slots_por_orientador:
            slots_por_orientador[orientador_id] = []
        slots_por_orientador[orientador_id].append((fecha, hora_inicio, hora_fin))
        
    # Overlap checking
    for o_id, intervals in slots_por_orientador.items():
        n = len(intervals)
        for idx1 in range(n):
            f1, s1, e1 = intervals[idx1]
            for idx2 in range(idx1 + 1, n):
                f2, s2, e2 = intervals[idx2]
                if f1 == f2:
                    if max(s1, s2) < min(e1, e2):
                        overlaps += 1
                        
    # Max weekly hours checking
    for (o_id, week_key), hours in horas_por_semana_orientador.items():
        max_h = max_horas_semanales.get(o_id, 40)
        if hours > max_h:
            exceeded_weekly_hours[(o_id, week_key)] = hours - max_h
            
    # Standard deviation of total hours
    if len(active_orientadores) > 1:
        hours_list = [horas_totales_orientador[o] for o in active_orientadores]
        mean_hours = sum(hours_list) / len(hours_list)
        variance = sum((h - mean_hours) ** 2 for h in hours_list) / len(hours_list)
        std_dev = variance ** 0.5
    else:
        std_dev = 0.0
        
    cobertura_pct = (assigned_slots / total_slots * 100.0) if total_slots > 0 else 0.0
    
    return {
        'total_slots': total_slots,
        'assigned_slots': assigned_slots,
        'empty_slots': empty_slots,
        'cobertura_pct': cobertura_pct,
        'invalid_availabilities': invalid_availabilities,
        'overlaps': overlaps,
        'exceeded_weekly_hours': exceeded_weekly_hours,
        'horas_totales_orientador': horas_totales_orientador,
        'std_dev_horas': std_dev
    }

def optimizar_horarios(barrio, fecha_inicio, fecha_fin, db_path=None, pop_size=100, generations=200, mutation_rate=0.15):
    """Runs a Genetic Algorithm to optimize staff schedules for a given neighborhood and date range."""
    if db_path is None:
        try:
            db_path = db_manager.DEFAULT_DB_PATH
        except AttributeError:
            db_path = "banquillo.db"

    print(f"Iniciando optimización para el barrio '{barrio}' del {fecha_inicio} al {fecha_fin}...")
    
    # 1. Load data
    orientadores_raw = db_manager.get_orientadores(db_path)
    turnos_raw = db_manager.get_turnos_requeridos_by_barrio(barrio, db_path)
    dispos_raw = db_manager.get_disponibilidades_by_barrio(barrio, db_path)
    
    orientadores = [row_to_dict(r) for r in orientadores_raw]
    turnos = [row_to_dict(r) for r in turnos_raw]
    dispos = [row_to_dict(r) for r in dispos_raw]
    
    # Max hours weekly lookup
    max_horas_semanales = {}
    for o in orientadores:
        max_horas_semanales[o['id']] = o['max_horas_semanales'] if o['max_horas_semanales'] is not None else 40
        
    # Date limits
    d_start = parse_date(fecha_inicio)
    d_end = parse_date(fecha_fin)
    
    # Filter turnos and disponibilidades within the date range
    filtered_turnos = []
    for t in turnos:
        t_date = parse_date(t['fecha'])
        if d_start <= t_date <= d_end:
            filtered_turnos.append(t)
            
    filtered_dispos = []
    for d in dispos:
        d_date = parse_date(d['fecha'])
        if d_start <= d_date <= d_end:
            filtered_dispos.append(d)
            
    # Group availabilities: orientador_id -> date -> list of (start_time, end_time)
    availabilities_by_orientador = {}
    for d in filtered_dispos:
        o_id = d['orientador_id']
        f_date = parse_date(d['fecha'])
        h_start = d['hora_inicio']
        h_end = d['hora_fin']
        
        if o_id not in availabilities_by_orientador:
            availabilities_by_orientador[o_id] = {}
        if f_date not in availabilities_by_orientador[o_id]:
            availabilities_by_orientador[o_id][f_date] = []
        availabilities_by_orientador[o_id][f_date].append((h_start, h_end))
        
    # Active orientadores for balancing (those who have at least one availability entry in this period)
    active_orientadores = list(availabilities_by_orientador.keys())
    
    # If no turnos are required, abort
    if not filtered_turnos:
        print("No hay turnos requeridos para optimizar en este rango de fechas y barrio.")
        return None
        
    # Get already committed assignments in the database (they won't be deleted)
    committed_assignments = obtener_asignaciones_comprometidas(barrio, fecha_inicio, fecha_fin, db_path)
    committed_by_turno = {}
    for t_id, o_id in committed_assignments:
        if t_id not in committed_by_turno:
            committed_by_turno[t_id] = []
        committed_by_turno[t_id].append(o_id)
        
    # Build slots structure (N slots if N people are required)
    slots = []
    for t in filtered_turnos:
        t_id = t['id']
        personas_requeridas = t['personas_requeridas']
        committed_list = committed_by_turno.get(t_id, [])
        
        for idx in range(personas_requeridas):
            if idx < len(committed_list):
                slots.append({
                    'turno_id': t_id,
                    'fecha': t['fecha'],
                    'hora_inicio': t['hora_inicio'],
                    'hora_fin': t['hora_fin'],
                    'slot_index': idx,
                    'committed': True,
                    'fixed_orientador_id': committed_list[idx]
                })
            else:
                slots.append({
                    'turno_id': t_id,
                    'fecha': t['fecha'],
                    'hora_inicio': t['hora_inicio'],
                    'hora_fin': t['hora_fin'],
                    'slot_index': idx,
                    'committed': False,
                    'fixed_orientador_id': None
                })
                
    # Precalculate candidates available for each slot
    slot_candidates = []
    for slot in slots:
        if slot['committed']:
            slot_candidates.append([slot['fixed_orientador_id']])
            continue
        slot_fecha = parse_date(slot['fecha'])
        slot_start = slot['hora_inicio']
        slot_end = slot['hora_fin']
        
        candidates = []
        for o_id in availabilities_by_orientador:
            if check_availability(o_id, slot_fecha, slot_start, slot_end, availabilities_by_orientador):
                candidates.append(o_id)
        slot_candidates.append(candidates)
        
    # 2. Genetic Algorithm Initialisation
    population = []
    for _ in range(pop_size):
        individual = []
        for i, slot in enumerate(slots):
            if slot['committed']:
                individual.append(slot['fixed_orientador_id'])
            else:
                candidates = slot_candidates[i]
                if candidates:
                    # Bias initialization to prefer assigning available people (90% chance)
                    if random.random() < 0.90:
                        individual.append(random.choice(candidates))
                    else:
                        individual.append(None)
                else:
                    individual.append(None)
        population.append(individual)
        
    # Evaluate initial fitnesses
    fitnesses = [
        calcular_fitness(ind, slots, availabilities_by_orientador, max_horas_semanales, active_orientadores)
        for ind in population
    ]
    
    best_fitness = min(fitnesses)
    best_individual = list(population[fitnesses.index(best_fitness)])
    
    elitism_size = max(2, int(pop_size * 0.05))
    
    # 3. Main Evolutionary Loop
    for gen in range(generations):
        sorted_indices = sorted(range(len(population)), key=lambda idx: fitnesses[idx])
        
        # Track best individual
        current_best_idx = sorted_indices[0]
        if fitnesses[current_best_idx] < best_fitness:
            best_fitness = fitnesses[current_best_idx]
            best_individual = list(population[current_best_idx])
            
        new_population = []
        
        # Elitism: carry over the best individuals directly
        for i in range(elitism_size):
            new_population.append(list(population[sorted_indices[i]]))
            
        # Breeding / Crossover and Mutation
        while len(new_population) < pop_size:
            p1 = tournament_selection(population, fitnesses)
            p2 = tournament_selection(population, fitnesses)
            
            # Crossover (crossover rate = 0.8)
            if random.random() < 0.8:
                c1, c2 = crossover(p1, p2, slots)
            else:
                c1, c2 = list(p1), list(p2)
                
            # Mutation
            c1 = mutate(c1, slot_candidates, slots, mutation_rate)
            c2 = mutate(c2, slot_candidates, slots, mutation_rate)
            
            new_population.append(c1)
            if len(new_population) < pop_size:
                new_population.append(c2)
                
        population = new_population[:pop_size]
        
        # Recalculate fitnesses
        fitnesses = [
            calcular_fitness(ind, slots, availabilities_by_orientador, max_horas_semanales, active_orientadores)
            for ind in population
        ]
        
    # Final evaluation of the population to find the absolute best
    sorted_indices = sorted(range(len(population)), key=lambda idx: fitnesses[idx])
    if fitnesses[sorted_indices[0]] < best_fitness:
        best_fitness = fitnesses[sorted_indices[0]]
        best_individual = list(population[sorted_indices[0]])
        
    # 4. Persistence and Cleanup
    limpiar_asignaciones_no_comprometidas(barrio, fecha_inicio, fecha_fin, db_path)
    guardar_asignaciones(best_individual, slots, db_path)
    
    # 5. Summary metrics
    analysis = analizar_resultado(best_individual, slots, availabilities_by_orientador, max_horas_semanales, active_orientadores)
    
    return {
        'best_individual': best_individual,
        'slots': slots,
        'fitness': best_fitness,
        'analysis': analysis,
        'orientadores': orientadores,
        'max_horas_semanales': max_horas_semanales,
        'active_orientadores': active_orientadores,
        'availabilities': availabilities_by_orientador
    }

if __name__ == '__main__':
    # Script de prueba
    db_file = os.path.join(BASE_DIR, "banquillo.db")
    barrio_test = "La Cumbre"
    start_date = "2025-12-01"
    end_date = "2025-12-31"
    
    if not os.path.exists(db_file):
        # Fallback to local file in current dir
        db_file = "banquillo.db"
        
    if not os.path.exists(db_file):
        print(f"Error: La base de datos no existe en la ruta.")
        sys.exit(1)
        
    res = optimizar_horarios(
        barrio=barrio_test,
        fecha_inicio=start_date,
        fecha_fin=end_date,
        db_path=db_file,
        pop_size=100,
        generations=200,
        mutation_rate=0.15
    )
    
    if res:
        analysis = res['analysis']
        print("\n" + "=" * 60)
        print("RESULTADOS DETALLADOS DE LA OPTIMIZACIÓN GENÉTICA")
        print("=" * 60)
        print(f"Barrio optimizado:             {barrio_test}")
        print(f"Rango de fechas:               {start_date} a {end_date}")
        print(f"Total de turnos/slots:         {analysis['total_slots']}")
        print(f"Slots con asignación exitosa:  {analysis['assigned_slots']}")
        print(f"Slots que quedaron vacíos:     {analysis['empty_slots']}")
        print(f"Cobertura de turnos lograda:   {analysis['cobertura_pct']:.2f}%")
        print("-" * 60)
        print(f"Penalización total (Fitness):  {res['fitness']:.2f}")
        print(f"Asignaciones inválidas:        {analysis['invalid_availabilities']}")
        print(f"Traslapes de orientadores:     {analysis['overlaps']}")
        print(f"Desviación estándar de horas:  {analysis['std_dev_horas']:.2f} horas")
        print("-" * 60)
        print("Horas semanales excedidas por orientador:")
        if not analysis['exceeded_weekly_hours']:
            print("  Ninguno excedió su límite semanal.")
        else:
            for (o_id, week_key), exceeded_h in analysis['exceeded_weekly_hours'].items():
                print(f"  Orientador ID {o_id} (Semana {week_key[1]}): +{exceeded_h:.2f} horas")
                
        print("-" * 60)
        print("Detalle de horas asignadas en el período:")
        nombres_dict = {o['id']: o['nombre'] for o in res['orientadores']}
        for o_id, horas in sorted(analysis['horas_totales_orientador'].items()):
            nombre = nombres_dict.get(o_id, f"Orientador {o_id}")
            max_h = res['max_horas_semanales'].get(o_id, 40)
            print(f"  - {nombre} (ID {o_id}): {horas:.2f} horas asignadas (Límite semanal: {max_h}h)")
        print("=" * 60)
    else:
        print("No se pudo ejecutar la optimización.")

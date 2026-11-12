extends Node2D
## Moves the Player rectangle with the arrow keys or a gamepad stick and
## keeps it inside the window.

const SPEED := 260.0

@onready var player: ColorRect = $Player


func _process(delta: float) -> void:
	var direction := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	var limit := get_viewport_rect().size - player.size
	player.position = (player.position + direction * SPEED * delta).clamp(Vector2.ZERO, limit)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_tree().quit()

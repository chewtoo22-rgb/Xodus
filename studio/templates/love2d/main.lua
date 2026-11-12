-- Move the square with the arrow keys or WASD; Escape quits.
local player = { x = 304, y = 164, size = 32, speed = 260 }

local function axis(negative, positive)
  local value = 0
  if love.keyboard.isDown(negative[1], negative[2]) then value = value - 1 end
  if love.keyboard.isDown(positive[1], positive[2]) then value = value + 1 end
  return value
end

local function clamp(value, low, high)
  return math.max(low, math.min(high, value))
end

function love.update(dt)
  local dx = axis({ "left", "a" }, { "right", "d" })
  local dy = axis({ "up", "w" }, { "down", "s" })
  if dx ~= 0 and dy ~= 0 then
    dx, dy = dx * 0.7071, dy * 0.7071
  end
  local width, height = love.graphics.getDimensions()
  player.x = clamp(player.x + dx * player.speed * dt, 0, width - player.size)
  player.y = clamp(player.y + dy * player.speed * dt, 0, height - player.size)
end

function love.draw()
  love.graphics.clear(0.08, 0.09, 0.12)
  love.graphics.setColor(0.36, 0.78, 1)
  love.graphics.rectangle("fill", player.x, player.y, player.size, player.size)
  love.graphics.setColor(1, 1, 1)
  love.graphics.print("Arrow keys / WASD to move, Esc to quit", 12, 12)
end

function love.keypressed(key)
  if key == "escape" then love.event.quit() end
end
